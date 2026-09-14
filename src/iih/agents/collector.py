"""采集智能体 Collector（doc-06 §3）· 最简归因版：人工提交路径 + 自动拉取路径。

人工提交不经定向任务化，直接从陈述 + 媒介推断信源与途径，组装溯源五要素，
产出「情报条目新建」提案；落账由状态机执行器执行（本智能体不直接写账）。
范围：仅文字载体（附件管线 IIH-01.09~11、实体提及 IIH-01.12 另行剥离）。

自动拉取（IIH-01.08）：途径 + 页面 HTML → 前置指纹去重 → 命中追加节点 / 未命中 LLM 抽取陈述。
"""

from datetime import UTC, datetime

from instructor import Instructor
from openai.types.completion import CompletionUsage
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from iih.agents.director import CollectionTask
from iih.ledger.models import IntelligenceItem, ItemMode, LlmCall, Medium, SourceType
from iih.ledger.proposal import (
    IntelligenceItemNewPayload,
    IntelligenceItemNewProposal,
    ItemProvenanceAppendPayload,
    ItemProvenanceAppendProposal,
    ProvenanceData,
)
from iih.tools.html_normalize import fingerprint, normalize

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


EXTRACTION_SYSTEM_PROMPT = """你是情报采集智能体的陈述抽取模块。
给定一个网页的正文文本与其来源（信源·途径），识别其中**最具情报价值的一条**陈述。

要求：
- statement：客观陈述句，描述事实而非评价；若页面无情报价值内容，返回空字符串；
- rationale：一句话说明为何选此陈述（依据记入提案）。"""


class StatementExtractionResult(BaseModel):
    """LLM 结构化陈述抽取输出。"""

    statement: str = Field(description="页面中最具情报价值的一条陈述；无则空字符串")
    rationale: str = Field(description="一句话抽取依据")


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
        self, *, task: CollectionTask, html: str
    ) -> IntelligenceItemNewProposal | ItemProvenanceAppendProposal | None:
        """自动拉取路径（doc-06 §3 + 前置过滤）。

        流程：
        1. normalize(html) → 归一化文本 + fingerprint
        2. 查 IntelligenceItem by content_fingerprint
        3. 命中：返回 ItemProvenanceAppendProposal（不调 LLM、不计量）
        4. 未命中：调 LLM 抽取陈述
           4a. statement 空：返回 None（计量已发生）
           4b. 非空：返回 IntelligenceItemNewProposal（mode=AUTOMATED, modality=webpage,
               medium=internet, source=task.source_name, outlet=task.outlet_name,
               original_snapshot=归一化文本, original_url=task.url, content_fingerprint=fp）
        """
        text = normalize(html)
        fp = fingerprint(text)

        existing = self.session.scalars(
            select(IntelligenceItem).where(IntelligenceItem.content_fingerprint == fp)
        ).first()
        if existing is not None:
            return ItemProvenanceAppendProposal(
                payload=ItemProvenanceAppendPayload(
                    item_id=existing.id,
                    source_name=task.source_name,
                    source_type=task.source_type,
                    outlet_name=task.outlet_name,
                    original_url=task.url,
                    collected_at=datetime.now(UTC),
                ),
                rationale=f"内容指纹命中既有条目 #{existing.id}，追加转引链节点",
            )

        extraction, completion = self.llm.chat.completions.create_with_completion(
            response_model=StatementExtractionResult,
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"信源：{task.source_name}\n途径：{task.outlet_name}\n正文：\n{text}"
                    ),
                },
            ],
            model=self.model,
        )
        self._meter(target="outlet_collection", usage=completion.usage)

        if not extraction.statement.strip():
            return None  # LLM 判定无情报价值内容

        return IntelligenceItemNewProposal(
            payload=IntelligenceItemNewPayload(
                statement=extraction.statement.strip(),
                mode=ItemMode.AUTOMATED,
                content_fingerprint=fp,
                original_url=task.url,
            ),
            provenance=ProvenanceData(
                modality_code="webpage",
                medium_code="internet",
                collected_at=datetime.now(UTC),
                original_snapshot=text,
                source_name=task.source_name,
                source_type=task.source_type,
                outlet_name=task.outlet_name,
            ),
            rationale=extraction.rationale,
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
