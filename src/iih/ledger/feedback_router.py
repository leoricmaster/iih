"""反馈路由（doc-05 §4 记账层）：类型化反馈校验、落账、按六类型分流（doc-02 §6）。

分流到信用通路的反馈由信用归因与信用计算器消费（IIH-01.06）；
处置动作（作废、重估、重评）与配置 / 迭代通路后续任务加厚。
"""

from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy.orm import Session

from iih.ledger.models import Feedback, FeedbackType, IntelligenceItem

TYPE_LABELS = {
    FeedbackType.VALID: "有效",
    FeedbackType.FACTUAL_ERROR: "事实错误",
    FeedbackType.DUPLICATE_NOISE: "重复 / 噪音",
    FeedbackType.IRRELEVANT: "不相关",
    FeedbackType.OUTDATED: "过期",
    FeedbackType.RATING_DISPUTE: "评级异议",
}


class FeedbackChannel(StrEnum):
    """反馈分流通路（doc-02 §6）：处置 + 三学习通路（信用 / 配置 / 迭代）。"""

    DISPOSITION = "disposition"  # 处置：对目标的即时动作（作废 / 重估 / 重评）
    CREDIT = "credit"  # 信用通路：信源信用（仅有效 / 事实错误）
    CONFIGURATION = "configuration"  # 配置通路：需求 / 采集配置
    ITERATION = "iteration"  # 迭代通路：智能体迭代


FEEDBACK_ROUTING: dict[FeedbackType, frozenset[FeedbackChannel]] = {
    # 有效：信用 ↑ + 配置正向微调
    FeedbackType.VALID: frozenset({FeedbackChannel.CREDIT, FeedbackChannel.CONFIGURATION}),
    # 事实错误：处置（作废并级联重估）+ 信用 ↓↓ + 迭代（核实收紧）
    FeedbackType.FACTUAL_ERROR: frozenset(
        {FeedbackChannel.DISPOSITION, FeedbackChannel.CREDIT, FeedbackChannel.ITERATION}
    ),
    # 不相关：配置（需求 / 采集修正）
    FeedbackType.IRRELEVANT: frozenset({FeedbackChannel.CONFIGURATION}),
    # 过期：配置（采集频率、时效参数）
    FeedbackType.OUTDATED: frozenset({FeedbackChannel.CONFIGURATION}),
    # 重复 / 噪音：迭代（审查去重 / 初筛）
    FeedbackType.DUPLICATE_NOISE: frozenset({FeedbackChannel.ITERATION}),
    # 评级异议：处置（评级重评）
    FeedbackType.RATING_DISPUTE: frozenset({FeedbackChannel.DISPOSITION}),
}


class FeedbackRejectedError(Exception):
    """反馈驳回：校验未通过，不落账。"""

    def __init__(self, reasons: list[str]) -> None:
        self.reasons = reasons
        super().__init__("；".join(reasons))


@dataclass(frozen=True)
class FeedbackSubmitResult:
    """反馈落账结果：反馈 ID + 分流通路。"""

    feedback_id: int
    item_id: int
    channels: frozenset[FeedbackChannel]


class FeedbackRouter:
    """反馈入口的记账层落账器：校验 → 落账 → 分流。"""

    def submit(
        self,
        *,
        item_id: int,
        feedback_type: FeedbackType,
        reason: str,
        session: Session,
    ) -> FeedbackSubmitResult:
        """快捷反馈口径（doc-07 §5）：一键反馈以「快捷 · {类型}」为默认理由；事实错误理由必填。"""
        reasons: list[str] = []

        item = session.get(IntelligenceItem, item_id)
        if item is None:
            reasons.append("情报条目不存在")
        if feedback_type is FeedbackType.FACTUAL_ERROR and not reason.strip():
            reasons.append("事实错误反馈必须填写理由")
        if reasons:
            raise FeedbackRejectedError(reasons)

        assert item is not None
        feedback = Feedback(
            item=item,
            feedback_type=feedback_type,
            reason=reason.strip() or f"快捷 · {TYPE_LABELS[feedback_type]}",
        )
        session.add(feedback)
        session.flush()
        feedback_id = feedback.id
        item_id = item.id
        session.commit()
        return FeedbackSubmitResult(
            feedback_id=feedback_id,
            item_id=item_id,
            channels=FEEDBACK_ROUTING[feedback_type],
        )
