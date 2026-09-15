"""审查智能体 Reviewer（doc-06 §4）· 相关性 + 有效性初筛 + 事件时效否决（IIH-03.01）。

读 Lead 态条目，对激活情报需求判断相关性，并做有效性初筛；产出审查提案——
通过为候选（PASS）或否决为噪音（REJECT）附理由。落账由状态机执行器执行（本智能体不直接写账）。

事件时效否决（IIH-03.01）：IR 配置 event_freshness 时，item.event_time 早于时效边界的
IR 从候选列表移除；全部 IR 过期或无激活 IR → 直接 REJECT IRRELEVANT。

范围外（后续里程碑加厚）：事件同一性（DUPLICATE 否决路径）、实体归一、图连通度参考变量。
"""

from datetime import UTC, datetime, timedelta

from openai.types.completion import CompletionUsage
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from iih.ledger.duration import parse_duration_to_seconds
from iih.ledger.models import (
    IntelligenceItem,
    IntelligenceRequirement,
    IntelligenceRequirementStatus,
    LlmCall,
    RejectionReasonEnum,
    ReviewDecisionEnum,
)
from iih.ledger.proposal import ReviewPayload, ReviewProposal

REVIEW_SYSTEM_PROMPT = """你是情报审查智能体。
给定一条线索（陈述）与若干激活情报需求（id + 内容规格），判断该线索是否应放行进入核实。

判断两维度：
1. 相关性：陈述是否命中任一激活情报需求的主题 / 关键词 / 信源偏好 / 时效范围；
2. 有效性：陈述是否客观、完整、非纯评价、非噪音。

输出要求：
- decision：pass（通过为候选）或 reject（否决为噪音）；
- matched_requirement_id：通过时填命中的激活情报需求 id；否决时为 null；
- reason_type：否决时填理由枚举——
  * irrelevant：与所有激活需求均不相关；
  * invalid：陈述不完整 / 非客观 / 纯评价 / 噪音；
  通过时为 null；
- rationale：一句话审查依据，将记入提案的「依据」。

边界：本里程碑不做事件同一性（duplicate）判定；如判定为同源纯重复，按 irrelevant 或 invalid 给理由。
输入可能附带消费方审查异议与理由（此前否决存疑）：重审时须结合异议理由独立重新判断，不默认服从原判或异议。
"""


class ReviewJudgmentResult(BaseModel):
    """LLM 结构化审查输出（instructor 按此 schema 校验）。"""

    decision: ReviewDecisionEnum = Field(description="pass 或 reject")
    reason_type: RejectionReasonEnum | None = Field(
        default=None, description="否决理由：irrelevant/invalid；通过时为 null"
    )
    matched_requirement_id: int | None = Field(
        default=None, description="通过时命中的激活情报需求 id；否决时为 null"
    )
    rationale: str = Field(description="一句话审查依据")


class Reviewer:
    """审查智能体执行器（判断层）：无状态、输出提案。"""

    AGENT_NAME = "reviewer"

    def __init__(self, llm, session: Session, model: str) -> None:
        self.llm = llm
        self.session = session
        self.model = model

    def review(self, item: IntelligenceItem, *, dispute_note: str | None = None) -> ReviewProposal:
        """对一条 Lead 态条目产出审查提案；异议重审时携 dispute_note（doc-02 §6）。

        无激活情报需求时直接否决为 IRRELEVANT（无需求即无相关性），不调 LLM、不计量。
        事件时效否决（IIH-03.01）：item.event_time 早于 IR 时效边界的 IR 从候选列表移除；
        全部 IR 过期 → 直接 REJECT IRRELEVANT。
        其余情形调 LLM 判断，产出 PASS 或 REJECT 提案。
        """
        active_irs = list(
            self.session.scalars(
                select(IntelligenceRequirement).where(
                    IntelligenceRequirement.status == IntelligenceRequirementStatus.ACTIVE
                )
            )
        )

        if not active_irs:
            return ReviewProposal(
                payload=ReviewPayload(
                    item_id=item.id,
                    decision=ReviewDecisionEnum.REJECT,
                    reason_type=RejectionReasonEnum.IRRELEVANT,
                    matched_requirement_id=None,
                ),
                rationale="无激活情报需求，无法判定相关性",
            )

        fresh_irs = self._filter_by_freshness(active_irs, item)
        if not fresh_irs:
            return ReviewProposal(
                payload=ReviewPayload(
                    item_id=item.id,
                    decision=ReviewDecisionEnum.REJECT,
                    reason_type=RejectionReasonEnum.IRRELEVANT,
                    matched_requirement_id=None,
                ),
                rationale="全部激活需求均因事件时效过期不匹配",
            )

        judgment = self.judge_statement(
            statement=item.statement,
            requirements=fresh_irs,
            target="item_review",
            dispute_note=dispute_note,
        )

        return ReviewProposal(
            payload=ReviewPayload(
                item_id=item.id,
                decision=judgment.decision,
                reason_type=judgment.reason_type,
                matched_requirement_id=judgment.matched_requirement_id,
            ),
            rationale=judgment.rationale,
        )

    def _filter_by_freshness(
        self, irs: list[IntelligenceRequirement], item: IntelligenceItem
    ) -> list[IntelligenceRequirement]:
        """事件时效过滤（IIH-03.01）：IR 配 event_freshness 且 item.event_time 早于时效边界则移除。

        IR.event_freshness 为空 → 不限时效，保留；
        item.event_time 为空 → 不卡时效（无事件时间不否决），保留。
        """
        if item.event_time is None:
            return irs
        now = datetime.now(UTC)
        event_time = item.event_time
        if event_time.tzinfo is None:
            event_time = event_time.replace(tzinfo=UTC)
        result: list[IntelligenceRequirement] = []
        for ir in irs:
            if not ir.event_freshness:
                result.append(ir)
                continue
            seconds = parse_duration_to_seconds(ir.event_freshness)
            if seconds is None:
                result.append(ir)  # 解析失败的配置降级为不限
                continue
            if event_time + timedelta(seconds=seconds) >= now:
                result.append(ir)
        return result

    def judge_statement(
        self,
        *,
        statement: str,
        requirements: list[IntelligenceRequirement],
        target: str = "statement_preview",
        dispute_note: str | None = None,
    ) -> ReviewJudgmentResult:
        """对一条陈述按给定需求集做审查预判（试采集预览路径，不产出提案、不落账）。"""
        ir_block = "\n".join(f"- #{ir.id}：{ir.name}（{ir.content_spec}）" for ir in requirements)
        dispute_block = f"\n\n消费方审查异议：{dispute_note}" if dispute_note else ""
        judgment, completion = self.llm.chat.completions.create_with_completion(
            response_model=ReviewJudgmentResult,
            messages=[
                {"role": "system", "content": REVIEW_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"线索陈述：{statement}\n\n激活情报需求：\n{ir_block}{dispute_block}"
                    ),
                },
            ],
            model=self.model,
        )
        self._meter(target=target, usage=completion.usage)
        return judgment

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
