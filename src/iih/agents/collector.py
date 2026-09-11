"""采集智能体 Collector（doc-06 §3）· 最简归因版：人工提交路径。

人工提交不经定向任务化，直接从陈述 + 媒介推断信源与途径，组装溯源五要素，
产出「情报条目新建」提案；落账由状态机执行器执行（本智能体不直接写账）。
范围：仅文字载体（附件管线 IIH-01.09~11、实体提及 IIH-01.12 另行剥离）。
"""

from datetime import UTC, datetime

from instructor import Instructor
from openai.types.completion import CompletionUsage
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from iih.ledger.models import ItemMode, LlmCall, Medium, SourceType
from iih.ledger.proposal import (
    IntelligenceItemNewPayload,
    IntelligenceItemNewProposal,
    ProvenanceData,
)

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
