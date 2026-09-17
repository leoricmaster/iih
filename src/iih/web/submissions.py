"""录入素材页（doc-07 §2.3、原型）：贴文字纪要或上传录音，抽取陈述落账为线索。"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.templating import Jinja2Templates
from instructor import Instructor
from sqlalchemy import CursorResult, select, update
from sqlalchemy.orm import Session, selectinload

from iih.agents.collector import Collector
from iih.config import get_settings
from iih.ledger.models import (
    Derivation,
    DerivationProducer,
    IntelligenceItem,
    ItemMode,
    Material,
    MaterialStatus,
    Medium,
    Modality,
)
from iih.ledger.state_machine import ProposalRejectedError, StateMachineExecutor
from iih.pipeline import process_material
from iih.tools.asr import make_tingwu_asr, relabel_speakers, speaker_hints, split_speakers
from iih.tools.snapshot_store import make_snapshot_store, material_key
from iih.web.context import STATUS_LABELS, base_context, register_template_filters
from iih.web.deps import get_llm_client, get_session
from iih.web.flash import redirect_with_flash

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = register_template_filters(Jinja2Templates(directory=TEMPLATES_DIR))

router = APIRouter()

RECENT_LIMIT = 10

AUDIO_EXTENSIONS = {"mp3", "wav", "m4a", "aac", "ogg", "opus", "flac", "amr"}

MATERIAL_STATUS_LABELS = {
    MaterialStatus.UPLOADED: "待加工",
    MaterialStatus.PROCESSING: "转写中",
    MaterialStatus.TRANSCRIBED: "待标记",
    MaterialStatus.EXTRACTING: "抽取中",
    MaterialStatus.COMPLETED: "已完成",
    MaterialStatus.PROCESS_FAILED: "转写失败",
    MaterialStatus.EXTRACT_FAILED: "抽取失败",
}


def _offline_mediums(session: Session) -> list[Medium]:
    """媒介下拉封闭集合；互联网为自动拉取、不经本页（doc-07 §2.3）。"""
    return list(
        session.scalars(select(Medium).where(Medium.code != "internet").order_by(Medium.id))
    )


def _recent_manual_items(session: Session) -> list[IntelligenceItem]:
    return list(
        session.scalars(
            select(IntelligenceItem)
            .where(IntelligenceItem.mode == ItemMode.MANUAL)
            .order_by(IntelligenceItem.created_at.desc(), IntelligenceItem.id.desc())
            .limit(RECENT_LIMIT)
        )
    )


def _recent_materials(session: Session) -> list[dict[str, Any]]:
    """近期素材行：挂最新转写稿与发言人清单（待标记表单 / 转写稿查看用）。"""
    materials = list(
        session.scalars(
            select(Material)
            .options(selectinload(Material.medium))
            .order_by(Material.collected_at.desc(), Material.id.desc())
            .limit(RECENT_LIMIT)
        )
    )
    if not materials:
        return []
    transcripts: dict[int, str] = {}
    rows = session.execute(
        select(Derivation.material_id, Derivation.output_text)
        .where(
            Derivation.material_id.in_([m.id for m in materials]),
            Derivation.output_text.isnot(None),
        )
        .order_by(Derivation.id)
    ).all()
    for material_id, text in rows:
        if text is not None:
            transcripts[material_id] = text
    return [
        {
            "m": m,
            "transcript": transcripts.get(m.id),
            "speakers": (
                [{"label": s, "hint": hint} for s, hint in speaker_hints(transcripts[m.id]).items()]
                if m.status is MaterialStatus.TRANSCRIBED and m.id in transcripts
                else []
            ),
        }
        for m in materials
    ]


def _latest_transcript(session: Session, material_id: int) -> Derivation | None:
    return session.scalars(
        select(Derivation)
        .where(Derivation.material_id == material_id, Derivation.output_text.isnot(None))
        .order_by(Derivation.id.desc())
    ).first()


def _kickoff(request: Request, material_id: int, asr, store) -> None:
    """即时推进一步（事件驱动优先）：失败不阻断，循环兜底自动重试。"""
    try:
        process_material(
            settings=get_settings(),
            session_factory=request.app.state.session_factory,
            llm=None,  # 上传/重试只走提交段，不调抽取 LLM
            asr=asr,
            store=store,
            material_id=material_id,
        )
    except Exception:
        pass


def _render(
    request: Request,
    session: Session,
    errors: list[str] | None = None,
    flash: str = "",
    form_medium: str = "",
    form_statement: str = "",
):
    return templates.TemplateResponse(
        request,
        "submissions.html",
        {
            **base_context(session, "submit"),
            "mediums": _offline_mediums(session),
            "items": _recent_manual_items(session),
            "materials": _recent_materials(session),
            "status_labels": STATUS_LABELS,
            "material_status_labels": MATERIAL_STATUS_LABELS,
            "errors": errors or [],
            "flash": flash,
            "form_medium": form_medium,
            "form_statement": form_statement,
        },
    )


@router.get("/submissions")
def submissions_page(request: Request, flash: str = "", session: Session = Depends(get_session)):
    return _render(request, session, flash=flash)


@router.get("/submissions/status")
def submissions_status(session: Session = Depends(get_session)):
    """近期素材在途状态（前端轮询用）：转写/抽取完成即触发页面刷新。"""
    materials = session.scalars(
        select(Material)
        .order_by(Material.collected_at.desc(), Material.id.desc())
        .limit(RECENT_LIMIT)
    ).all()
    return [{"id": m.id, "status": m.status.value} for m in materials]


@router.post("/submissions")
def submit(
    request: Request,
    medium_code: str = Form(""),
    statement: str = Form(""),
    files: list[UploadFile] = File(default=[]),
    session: Session = Depends(get_session),
    llm: Instructor = Depends(get_llm_client),
):
    """统一提交（原型「提交素材」box）：文字纪要走抽取落账，音频附件建素材即时提交转写。"""

    def fail(reasons: list[str]):
        return _render(request, session, reasons, form_medium=medium_code, form_statement=statement)

    uploads = [f for f in files if f is not None and (f.filename or "").strip()]
    text = statement.strip()
    errors: list[str] = []
    if not medium_code:
        errors.append("请选择媒介")
    bad = [
        f for f in uploads if (f.filename or "").rsplit(".", 1)[-1].lower() not in AUDIO_EXTENSIONS
    ]
    if bad:
        errors.append("仅支持音频文件（图片 / 文档暂不支持）")
    if not text and not uploads:
        errors.append("请上传附件，或填写文字纪要")
    if not errors and medium_code == "internet":
        errors.append("互联网媒介为自动拉取，不经本页录入")
    asr = make_tingwu_asr(get_settings())
    if not errors and uploads and asr is None:
        errors.append("听悟 ASR 未配置，暂不能接收录音")

    if errors:
        return fail(errors)

    messages: list[str] = []

    if uploads:
        medium = session.scalars(select(Medium).where(Medium.code == medium_code)).first()
        modality = session.scalars(select(Modality).where(Modality.code == "audio")).first()
        if medium is None or modality is None:
            return fail(["媒介不存在"])
        store = make_snapshot_store(get_settings())
        uploaded = 0
        duplicates = 0
        for upload in uploads:
            filename = upload.filename or ""
            ext = filename.rsplit(".", 1)[-1].lower()
            data = upload.file.read()
            key = material_key(data, ext)
            if session.scalars(select(Material).where(Material.object_key == key)).first():
                duplicates += 1
                continue
            material = Material(
                modality_id=modality.id,
                medium_id=medium.id,
                collected_at=datetime.now(UTC),
                object_key=store.put_material(data, ext),
                filename=filename[:500],
                status=MaterialStatus.UPLOADED,
            )
            session.add(material)
            session.commit()
            _kickoff(request, material.id, asr, store)
            uploaded += 1
        if uploaded:
            message = f"录音已上传 {uploaded} 个，转写中"
            if duplicates:
                message += f"；{duplicates} 个与既有素材重复，未重复上传"
            messages.append(message)
        elif duplicates:
            messages.append(f"{duplicates} 个附件与既有素材重复，未重复上传")

    if text:
        collector = Collector(llm=llm, session=session, model=get_settings().llm_model)
        try:
            proposals = collector.submit_manual(medium_code=medium_code, statement=text)
        except ValueError as exc:
            return fail([str(exc)])
        if not proposals:
            return fail(["未能从提交文本中识别出情报陈述"])

        created = 0
        failed = 0
        reject_reasons: list[str] = []
        for proposal in proposals:
            try:
                StateMachineExecutor().execute(proposal, session=session)
                created += 1
            except ProposalRejectedError as exc:
                failed += 1
                reject_reasons.extend(exc.reasons)
        if not created:
            return fail(reject_reasons or ["落账失败"])

        message = f"已提交：抽取陈述 {created} 条，进入流水线"
        if failed:
            message += f"；{failed} 条落账失败"
        messages.append(message)

    return redirect_with_flash("/submissions", "；".join(messages))


@router.post("/materials/{material_id}/retry")
def retry_material(material_id: int, request: Request, session: Session = Depends(get_session)):
    """人工重试：清重试计数与失败原因，交回循环自动推进（达上限转人工后的人口）。"""
    result = cast(
        "CursorResult[Any]",
        session.execute(
            update(Material)
            .where(
                Material.id == material_id,
                Material.status.in_((MaterialStatus.PROCESS_FAILED, MaterialStatus.EXTRACT_FAILED)),
            )
            .values(retry_count=0, failure_reason=None)
        ),
    )
    session.commit()
    if result.rowcount != 1:
        return redirect_with_flash("/submissions", "素材不在失败态，无需重试")

    settings = get_settings()
    asr = make_tingwu_asr(settings)
    if asr is not None:
        _kickoff(request, material_id, asr, make_snapshot_store(settings))
    return redirect_with_flash("/submissions", "已重试")


@router.post("/materials/{material_id}/mark")
async def mark_speakers(
    material_id: int, request: Request, session: Session = Depends(get_session)
):
    """发言人标记：全部发言人实名替换转写稿（追加人工派生）→ 抽取中；标记完成转写稿才算完成。"""
    material = session.get(Material, material_id)
    if material is None or material.status is not MaterialStatus.TRANSCRIBED:
        return redirect_with_flash("/submissions", "素材不在待标记状态", param="err")
    form = await request.form()
    marks = {k: v.strip()[:80] for k, v in form.items() if isinstance(v, str) and v.strip()}
    derivation = _latest_transcript(session, material_id)
    if derivation is None or not marks:
        return redirect_with_flash("/submissions", "未填写任何发言人实名", param="err")
    missing = {s for s, _ in split_speakers(derivation.output_text or "") if s} - marks.keys()
    if missing:
        names = "、".join(sorted(missing))
        return redirect_with_flash(
            "/submissions", f"还有 {len(missing)} 位发言人未填实名：{names}", param="err"
        )

    claimed = cast(
        "CursorResult[Any]",
        session.execute(
            update(Material)
            .where(Material.id == material_id, Material.status == MaterialStatus.TRANSCRIBED)
            .values(status=MaterialStatus.EXTRACTING)
        ),
    )
    if claimed.rowcount != 1:
        session.rollback()
        return redirect_with_flash("/submissions", "素材不在待标记状态", param="err")
    session.add(
        Derivation(
            material_id=material_id,
            parent_id=derivation.id,
            producer=DerivationProducer.HUMAN,
            producer_ref="speaker-mark",
            output_text=relabel_speakers(derivation.output_text or "", marks),
        )
    )
    session.commit()
    return redirect_with_flash("/submissions", f"已标记 {len(marks)} 位发言人，抽取中")


@router.post("/materials/{material_id}/transcript")
async def edit_transcript(
    material_id: int, request: Request, session: Session = Depends(get_session)
):
    """转写稿编辑：追加人工派生为最新权威；已完成素材可「保存并重新抽取」（撤回旧线索由重抽替换）。"""
    material = session.get(Material, material_id)
    if material is None or material.status not in (
        MaterialStatus.TRANSCRIBED,
        MaterialStatus.COMPLETED,
    ):
        return redirect_with_flash("/submissions", "素材不在可编辑状态", param="err")
    form = await request.form()
    transcript_value = form.get("transcript")
    transcript = transcript_value.strip() if isinstance(transcript_value, str) else ""
    if not transcript:
        return redirect_with_flash("/submissions", "转写稿为空，未保存", param="err")
    derivation = _latest_transcript(session, material_id)
    if derivation is None:
        return redirect_with_flash("/submissions", "无可编辑的转写稿", param="err")

    respecify = form.get("respecify") == "on" and material.status is MaterialStatus.COMPLETED
    session.add(
        Derivation(
            material_id=material_id,
            parent_id=derivation.id,
            producer=DerivationProducer.HUMAN,
            producer_ref="transcript-edit",
            output_text=transcript,
        )
    )
    if respecify:
        session.execute(
            update(IntelligenceItem)
            .where(IntelligenceItem.material_id == material_id)
            .values(retracted=True, content_fingerprint=None)
        )
        claimed = (
            cast(
                "CursorResult[Any]",
                session.execute(
                    update(Material)
                    .where(Material.id == material_id, Material.status == MaterialStatus.COMPLETED)
                    .values(status=MaterialStatus.EXTRACTING)
                ),
            ).rowcount
            == 1
        )
        if not claimed:
            session.rollback()
            return redirect_with_flash("/submissions", "素材状态已变化，未重抽", param="err")
    session.commit()

    if respecify:
        return redirect_with_flash("/submissions", "转写稿已保存，将重新抽取")
    return redirect_with_flash("/submissions", "转写稿已保存")
