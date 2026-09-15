"""采集智能体 Collector（doc-06 §3）· 最简归因版：人工提交路径 + 自动拉取路径。

人工提交不经定向任务化，直接从陈述 + 媒介推断信源与途径，组装溯源五要素，
产出「情报条目新建」提案；落账由状态机执行器执行（本智能体不直接写账）。
范围：仅文字载体（附件管线 IIH-01.09~11、实体提及 IIH-01.12 另行剥离）。

自动拉取（IIH-01.15 两跳）：入口页选链 → 抓文章页 → 文章页抽陈述；
原文 URL 即实际抓取的文章页地址（确定性），原文快照为原始 HTML 存对象存储。
"""

from collections.abc import Callable
from datetime import UTC, datetime

from instructor import Instructor
from openai.types.completion import CompletionUsage
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from iih.agents.director import CollectionTask
from iih.ledger.models import (
    IntelligenceItem,
    ItemMode,
    LlmCall,
    Medium,
    Outlet,
    ProvenanceChainNode,
    Source,
    SourceType,
)
from iih.ledger.proposal import (
    IntelligenceItemNewPayload,
    IntelligenceItemNewProposal,
    ItemProvenanceAppendPayload,
    ItemProvenanceAppendProposal,
    ProvenanceData,
)
from iih.tools.html_normalize import extract_link_candidates, fingerprint, normalize
from iih.tools.snapshot_store import SnapshotStore

ATTRIBUTION_SYSTEM_PROMPT = """你是情报采集智能体的归因模块。
给定一条情报陈述与其获取媒介，推断信源与发布途径。

要求：
- source_name：发布主体（谁在说），从陈述中的公司 / 机构 / 人物推断；
- source_type：主体类型；
- outlet_name：该场景下的具体发布出口（如「渠道大会现场」），无法推断则留空；
- rationale：一句话归因依据，将记入提案的「依据」。"""


class AttributionResult(BaseModel):
    """LLM 结构化归因输出（instructor 按此 schema 校验）。"""

    source_name: str = Field(description="发布主体名，如「W 公司」")
    source_type: SourceType = Field(
        description="主体类型：company/government/organization/media/person/other"
    )
    outlet_name: str | None = Field(
        default=None, description="发布出口，如「渠道大会现场」；无法推断留空"
    )
    rationale: str = Field(description="一句话归因依据")


ARTICLE_SELECTION_SYSTEM_PROMPT = """你是情报采集智能体的选链模块。
给定途径入口页（多为列表页 / 首页）的正文文本与候选链接清单（链接 + 锚文本），
判断入口页本身是否已是文章正文页；若不是，选出一条最值得作为本次采集对象的文章页链接。

要求：
- url：入口页即文章正文页时返回空字符串；否则从候选清单中选一条与页面主题最相关的
  文章 / 详情页链接（原文照抄清单中的链接，不得自造）；
- rationale：一句话选链依据。"""


class ArticleSelectionResult(BaseModel):
    """LLM 结构化选链输出。"""

    url: str = Field(default="", description="选中的文章页链接；入口页即文章页时为空字符串")
    rationale: str = Field(description="一句话选链依据")


EXTRACTION_SYSTEM_PROMPT = """你是情报采集智能体的陈述抽取模块。
给定文章页的正文文本与其来源（信源·途径），识别其中**最具情报价值的一条**陈述。

要求：
- statement：客观陈述句，描述事实而非评价；若页面无情报价值内容，返回空字符串；
- event_time：陈述所述事实的发生日期（ISO 格式，如 2026-08-30），正文无明确日期
  依据则留空，不得编造；
- rationale：一句话说明为何选此陈述（依据记入提案）。"""


class StatementExtractionResult(BaseModel):
    """LLM 结构化陈述抽取输出。"""

    statement: str = Field(description="页面中最具情报价值的一条陈述；无则空字符串")
    event_time: datetime | None = Field(
        default=None, description="陈述所述事实的发生日期；正文无明确日期依据则留空"
    )
    rationale: str = Field(description="一句话抽取依据")


def _as_utc(value: datetime | None) -> datetime | None:
    """LLM 输出的 naive 时间按 UTC 入账（库内时间戳一律 aware UTC）。"""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


class Collector:
    """采集智能体执行器（判断层）：无状态、输出提案。"""

    AGENT_NAME = "collector"

    def __init__(self, llm: Instructor, session: Session, model: str) -> None:
        self.llm = llm
        self.session = session
        self.model = model

    def submit_manual(self, *, medium_code: str, statement: str) -> IntelligenceItemNewProposal:
        """人工提交路径：陈述 + 媒介 → LLM 最简归因 → 线索提案（doc-07 §2.3）。"""
        medium = self.session.scalars(select(Medium).where(Medium.code == medium_code)).first()
        if medium is None:
            raise ValueError(f"媒介不存在：{medium_code}")

        attribution, completion = self.llm.chat.completions.create_with_completion(
            response_model=AttributionResult,
            messages=[
                {"role": "system", "content": ATTRIBUTION_SYSTEM_PROMPT},
                {"role": "user", "content": f"媒介：{medium.name}\n陈述：{statement}"},
            ],
            model=self.model,
        )
        self._meter(target="manual_submission", usage=completion.usage)

        return IntelligenceItemNewProposal(
            payload=IntelligenceItemNewPayload(
                statement=statement,
                mode=ItemMode.MANUAL,
            ),
            provenance=ProvenanceData(
                modality_code="text",  # 本故事范围：仅文字载体
                medium_code=medium_code,
                collected_at=datetime.now(UTC),
                original_snapshot=statement,  # 文字载体：原文快照 = 提交文本
                source_name=attribution.source_name,
                source_type=attribution.source_type,
                outlet_name=attribution.outlet_name or None,
            ),
            rationale=attribution.rationale,
        )

    def collect_outlet(
        self,
        *,
        task: CollectionTask,
        html: str,
        fetch_article: Callable[[str], str],
        store: SnapshotStore | None = None,
    ) -> IntelligenceItemNewProposal | ItemProvenanceAppendProposal | None:
        """自动拉取路径（doc-06 §3 两跳 + 前置过滤）。

        流程：
        1. 选链（LLM）：入口页多为列表/首页——判本页是否即文章页，否则选一条文章链接
        2. 单跳回退：入口页即文章页，直接以本页为文章页
        3. URL 级去重（确定性）：选链命中已采 URL → 追加节点提案，不抓取不抽取
        4. 抓文章页（fetch_article）→ 归一化文本 + 内容指纹
        5. 指纹命中：追加节点提案（不调抽取 LLM）
        6. 抽取陈述（LLM）：空 → None（计量已发生）；非空 → 新建提案
           （原文 URL = 文章页地址；原始 HTML 经 store 存对象存储，键入提案）
        """
        entry_text = normalize(html)
        candidates = extract_link_candidates(html, base_url=task.url)
        block = (
            "\n".join(f"- {url} ｜ {text or '（无锚文本）'}" for url, text in candidates)
            if candidates
            else "（无）"
        )
        selection, completion = self.llm.chat.completions.create_with_completion(
            response_model=ArticleSelectionResult,
            messages=[
                {"role": "system", "content": ARTICLE_SELECTION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"信源：{task.source_name}\n途径：{task.outlet_name}"
                        f"\n入口页正文：\n{entry_text}\n\n候选链接清单：\n{block}"
                    ),
                },
            ],
            model=self.model,
            temperature=0,  # 选链需可复现：试采与正式运行同输入应同输出
        )
        self._meter(target="outlet_link_select", usage=completion.usage)

        article_url = selection.url.strip()
        if not article_url or article_url == task.url:
            return self._collect_article(
                task=task, url=task.url, html=html, text=entry_text, store=store
            )

        existing = self.session.scalars(
            select(IntelligenceItem).where(IntelligenceItem.original_url == article_url)
        ).first()
        if existing is not None:
            return self._append_or_none(
                existing_id=existing.id, task=task, original_url=article_url
            )

        article_html = fetch_article(article_url)
        return self._collect_article(
            task=task,
            url=article_url,
            html=article_html,
            text=normalize(article_html),
            store=store,
        )

    def _collect_article(
        self,
        *,
        task: CollectionTask,
        url: str,
        html: str,
        text: str,
        store: SnapshotStore | None,
    ) -> IntelligenceItemNewProposal | ItemProvenanceAppendProposal | None:
        """文章页采集：指纹去重 → 抽取陈述 → 新建提案（原文 URL = 本页地址）。"""
        fp = fingerprint(text)
        existing = self.session.scalars(
            select(IntelligenceItem).where(IntelligenceItem.content_fingerprint == fp)
        ).first()
        if existing is not None:
            return self._append_or_none(existing_id=existing.id, task=task, original_url=url)

        user_content = f"信源：{task.source_name}\n途径：{task.outlet_name}\n正文：\n{text}"
        extraction, completion = self.llm.chat.completions.create_with_completion(
            response_model=StatementExtractionResult,
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            model=self.model,
            temperature=0,  # 抽取需可复现：同输入应同输出
        )
        self._meter(target="outlet_collection", usage=completion.usage)

        if not extraction.statement.strip():
            return None  # LLM 判定无情报价值内容

        return IntelligenceItemNewProposal(
            payload=IntelligenceItemNewPayload(
                statement=extraction.statement.strip(),
                mode=ItemMode.AUTOMATED,
                event_time=_as_utc(extraction.event_time),
                content_fingerprint=fp,
                original_url=url,
                snapshot_object_key=store.put_html(html) if store is not None else None,
            ),
            provenance=ProvenanceData(
                modality_code="webpage",
                medium_code="internet",
                collected_at=datetime.now(UTC),
                source_name=task.source_name,
                source_type=task.source_type,
                outlet_name=task.outlet_name,
            ),
            rationale=extraction.rationale,
        )

    def _append_or_none(
        self, *, existing_id: int, task: CollectionTask, original_url: str
    ) -> ItemProvenanceAppendProposal | None:
        """命中既有条目时追加转引链节点；节点已存在（本轮无新内容）返回 None。"""
        source = self.session.scalars(select(Source).where(Source.name == task.source_name)).first()
        outlet = (
            self.session.scalars(
                select(Outlet).where(Outlet.source_id == source.id, Outlet.name == task.outlet_name)
            ).first()
            if source is not None and task.outlet_name
            else None
        )
        if source is not None and (not task.outlet_name or outlet is not None):
            linked = self.session.scalars(
                select(ProvenanceChainNode).where(
                    ProvenanceChainNode.item_id == existing_id,
                    ProvenanceChainNode.source_id == source.id,
                    ProvenanceChainNode.outlet_id == (outlet.id if outlet else None),
                )
            ).first()
            if linked is not None:
                return None
        return ItemProvenanceAppendProposal(
            payload=ItemProvenanceAppendPayload(
                item_id=existing_id,
                source_name=task.source_name,
                source_type=task.source_type,
                outlet_name=task.outlet_name,
                original_url=original_url,
                collected_at=datetime.now(UTC),
            ),
            rationale=f"已采集内容命中既有条目 #{existing_id}，追加转引链节点",
        )

    def _meter(self, *, target: str, usage: CompletionUsage) -> None:
        """调用计量即时入账：LLM 成本在调用时已发生，与提案成败无关（技术架构 §1）。"""
        self.session.add(
            LlmCall(
                agent=self.AGENT_NAME,
                target=target,
                model=self.model,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
            )
        )
        self.session.commit()
