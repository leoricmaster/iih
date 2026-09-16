"""听悟 ASR 适配器（工具层·录音管线，doc-06 §3）：OSS 中转 → 离线转写任务 → 段落转写稿。

听悟读不了私有地址，音频须经阿里云 OSS 中转（签名 URL 提交，完结后清理临时对象；
进程重启丢内存映射时临时对象可能残留，量小可容忍）。说话人分离开启（发言人标记
入转写稿，供采集智能体归因）；听悟摘要关闭——摘要属判断层（采集智能体 LLM 抽取）。
"""

import hashlib
import json
import re
import urllib.request
from dataclasses import dataclass
from typing import Any

import oss2
from alibabacloud_tea_openapi import models as openapi_models
from alibabacloud_tingwu20230930 import models as tingwu_models
from alibabacloud_tingwu20230930.client import Client as TingwuClient

TINGWU_ENDPOINT = "tingwu.cn-beijing.aliyuncs.com"
DONE_STATUSES = {"COMPLETED", "SUCCEEDED", "TranscriptionCompleted"}
FAILED_STATUSES = {"FAILED", "CANCELED", "TranscriptionFailed"}

# 转写稿行格式（说话人分离）：[mm:ss] 发言人N：文本
SPEAKER_LINE_RE = re.compile(r"^\[(\d{2,}):(\d{2})\] (.+?)：", re.MULTILINE)


class TingwuAsrError(Exception):
    """转写任务失败：提交 / 查询 / 解析任一环节的不可恢复错误。"""


@dataclass(frozen=True)
class TranscriptionResult:
    """转写产出：段落转写稿（[mm:ss] 发言人N：文本）+ 音频时长（派生行计量）。"""

    text: str
    duration_seconds: int


class TingwuAsr:
    """听悟离线转写客户端：submit 提交任务，check 单次查询（轮询归编排层）。"""

    def __init__(
        self,
        *,
        access_key_id: str,
        access_key_secret: str,
        app_key: str,
        oss_bucket: str,
        oss_region: str,
        region_id: str,
    ) -> None:
        if not all([access_key_id, access_key_secret, app_key, oss_bucket]):
            raise TingwuAsrError("听悟 ASR 未配置（AK / AppKey / OSS 桶）")
        self._ak_id = access_key_id
        self._ak_secret = access_key_secret
        self._app_key = app_key
        self._oss_bucket = oss_bucket
        self._oss_region = oss_region
        self._region_id = region_id
        self._client = TingwuClient(
            openapi_models.Config(
                access_key_id=access_key_id,
                access_key_secret=access_key_secret,
                region_id=region_id,
                endpoint=TINGWU_ENDPOINT,
            )
        )
        self._oss_keys: dict[str, str] = {}  # task_id → OSS 临时对象键（完结清理用）

    def submit(self, audio: bytes, filename: str) -> str:
        """OSS 中转上传 + 提交离线转写任务（说话人分离开、摘要关），返回任务号。"""
        suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
        digest = hashlib.sha256(audio).hexdigest()
        oss_key = f"iih-asr/{digest}.{suffix}"
        try:
            bucket = self._bucket()
            bucket.put_object(oss_key, audio)
            file_url = bucket.sign_url("GET", oss_key, 86400, slash_safe=True).replace(
                "http://", "https://"
            )
        except Exception as exc:
            raise TingwuAsrError(f"OSS 中转上传失败：{exc}") from exc

        try:
            resp = self._client.create_task(
                tingwu_models.CreateTaskRequest(
                    app_key=self._app_key,
                    input=tingwu_models.CreateTaskRequestInput(
                        file_url=file_url,
                        source_language="cn",
                        language_hints=["cn", "en"],
                    ),
                    parameters=tingwu_models.CreateTaskRequestParameters(
                        transcription=tingwu_models.CreateTaskRequestParametersTranscription(
                            diarization_enabled=True,
                            diarization=tingwu_models.CreateTaskRequestParametersTranscriptionDiarization(
                                speaker_count=0,
                            ),
                        ),
                    ),
                    type="offline",
                )
            )
        except Exception as exc:
            raise TingwuAsrError(f"听悟任务提交失败：{exc}") from exc

        body = resp.body
        if str(body.code) != "0":
            raise TingwuAsrError(f"听悟任务提交失败：code={body.code} msg={body.message}")
        task_id = body.data.task_id
        self._oss_keys[task_id] = oss_key
        return task_id

    def check(self, task_id: str) -> TranscriptionResult | None:
        """单次查询：未完成 None；失败抛 TingwuAsrError；完成返回转写稿并清理中转对象。"""
        try:
            resp = self._client.get_task_info(task_id)
        except Exception as exc:
            raise TingwuAsrError(f"听悟任务查询失败：{exc}") from exc

        data = resp.body.data if resp.body is not None else None
        status = data.task_status if data is not None else None
        if status in FAILED_STATUSES:
            error = getattr(data, "error_message", None) or ""
            raise TingwuAsrError(f"转写任务失败：{status} {error}".strip())
        if status not in DONE_STATUSES:
            return None

        result = getattr(data, "result", None)
        if not result:
            raise TingwuAsrError(f"转写任务无结果：{task_id}")
        self._cleanup(task_id)
        return self._parse_result(result)

    def _bucket(self) -> oss2.Bucket:
        auth = oss2.AuthV4(self._ak_id, self._ak_secret)
        return oss2.Bucket(
            auth, f"oss-{self._oss_region}.aliyuncs.com", self._oss_bucket, region=self._oss_region
        )

    def _cleanup(self, task_id: str) -> None:
        """完结后清理 OSS 临时对象（尽力而为，失败不阻断结果交付）。"""
        oss_key = self._oss_keys.pop(task_id, None)
        if oss_key is None:
            return
        try:
            self._bucket().delete_object(oss_key)
        except Exception:
            pass

    def _parse_result(self, result: object) -> TranscriptionResult:
        """听悟结果 JSON（Transcription 为下载 URL）→ 段落转写稿 + 时长。"""
        try:
            data: Any = json.loads(result) if isinstance(result, str) else result
            if hasattr(data, "to_map"):
                data = data.to_map()
            transcription = data.get("Transcription") or {}
            if isinstance(transcription, str) and transcription.startswith("http"):
                transcription = json.loads(urllib.request.urlopen(transcription).read())
            if isinstance(transcription, dict) and "Transcription" in transcription:
                transcription = transcription.get("Transcription") or {}
        except Exception as exc:
            raise TingwuAsrError(f"转写结果解析失败：{exc}") from exc

        duration_ms = (transcription.get("AudioInfo") or {}).get("Duration") or 0
        lines = []
        for paragraph in transcription.get("Paragraphs") or []:
            words = paragraph.get("Words") or []
            if not words:
                continue
            text = "".join(w.get("Text", "") for w in words)
            begin_s = int(words[0].get("Start", 0)) // 1000
            mm, ss = divmod(begin_s, 60)
            speaker = paragraph.get("SpeakerId") or "?"
            lines.append(f"[{mm:02d}:{ss:02d}] 发言人{speaker}：{text}")
        if not lines:
            raise TingwuAsrError("转写结果无段落内容")
        return TranscriptionResult(text="\n".join(lines), duration_seconds=int(duration_ms / 1000))


def split_speakers(text: str) -> list[tuple[str, str]]:
    """转写稿按发言人聚合切段：同发言人各行归一段（首现顺序），逐发言人归因用。

    无发言人前缀的行归入当前发言人段（开头散行归匿名段）；整稿无前缀则返回单一匿名段。
    """
    order: list[str] = []
    parts: dict[str, list[str]] = {}
    current = ""
    for line in text.splitlines():
        matched = SPEAKER_LINE_RE.match(line)
        if matched is not None:
            current = matched.group(3)
        if current not in parts:
            parts[current] = []
            order.append(current)
        parts[current].append(line)
    return [(speaker, "\n".join(parts[speaker])) for speaker in order]


def speaker_hints(text: str, *, max_lines: int = 2, max_chars: int = 100) -> dict[str, str]:
    """每位发言人开头发言片段（去时间戳与发言人前缀，首现顺序）：标记表单认人上下文。"""

    hints: dict[str, str] = {}
    for speaker, segment in split_speakers(text):
        if not speaker or speaker in hints:
            continue
        contents: list[str] = []
        for line in segment.splitlines():
            matched = SPEAKER_LINE_RE.match(line)
            content = line[matched.end() :].strip() if matched else line.strip()
            if content:
                contents.append(content)
            if len(contents) == max_lines:
                break
        hint = " / ".join(contents)
        if len(hint) > max_chars:
            hint = hint[: max_chars - 1] + "…"
        hints[speaker] = hint
    return hints


def relabel_speakers(text: str, marks: dict[str, str]) -> str:
    """按映射把转写稿发言人标签替换为实名（发言人N → 实名）；映射外标签保留。"""

    def _sub(matched: re.Match[str]) -> str:
        name = marks.get(matched.group(3))
        return f"[{matched.group(1)}:{matched.group(2)}] {name or matched.group(3)}："

    return SPEAKER_LINE_RE.sub(_sub, text)


def make_tingwu_asr(settings) -> TingwuAsr | None:
    """按运行时配置构造听悟客户端；未配置返回 None（素材段跳过，上传端点拒收）。"""
    if not all(
        [
            settings.aliyun_access_key_id,
            settings.aliyun_access_key_secret,
            settings.tingwu_app_key,
            settings.oss_bucket,
        ]
    ):
        return None
    return TingwuAsr(
        access_key_id=settings.aliyun_access_key_id,
        access_key_secret=settings.aliyun_access_key_secret,
        app_key=settings.tingwu_app_key,
        oss_bucket=settings.oss_bucket,
        oss_region=settings.oss_region,
        region_id=settings.tingwu_region_id,
    )
