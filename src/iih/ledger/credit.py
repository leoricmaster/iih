"""信用计算器与信用归因（doc-04 §2.3、decision-04、doc-05 §4 记账层）。

信用归因本里程碑为确定性查找（转引链最早引入陈述的信源 = 责任信源），
结果经 CreditAdjustment 落档可追溯；信用计算为确定性公式，版本化、可重放。
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from iih.ledger.models import (
    CreditAdjustment,
    FeedbackType,
    IntelligenceItem,
    ProvenanceChainNode,
    Source,
)

SOURCE_CREDIT_FORMULA_VERSION = "source_credit_v1"

VALID_DELTA = 1  # 有效反馈 +1
FACTUAL_ERROR_DELTA = -2  # 事实错误 −2
HALF_LIFE_DAYS = 180  # 半衰期（天）

# 分档阈值（宽容制，自上而下首个命中）：分数区间 → 信源信用档
CREDIT_GRADE_THRESHOLDS: tuple[tuple[float, str], ...] = (
    (8.0, "A"),
    (4.0, "B"),
    (0.0, "C"),
    (-4.0, "D"),
    (-8.0, "E"),
)


def credit_delta(feedback_type: FeedbackType) -> int | None:
    """信用通路奖惩分：仅有效 / 事实错误有值（doc-02 §6），其余类型为 None。"""
    if feedback_type is FeedbackType.VALID:
        return VALID_DELTA
    if feedback_type is FeedbackType.FACTUAL_ERROR:
        return FACTUAL_ERROR_DELTA
    return None


def compute_credit_score(adjustments: list[tuple[int, datetime]], *, at: datetime) -> float:
    """半衰期累计分：score(at) = Σ delta_i · 2^(−(at − t_i)/180d)（doc-04 §2.3）。

    同一调整历史 + 同一评估时点 → 同一分数（可重放）。
    """
    score = 0.0
    for delta, occurred_at in adjustments:
        age_days = (at - occurred_at).total_seconds() / 86400
        score += delta * 2 ** (-age_days / HALF_LIFE_DAYS)
    return score


def score_to_grade(score: float) -> str:
    """累计分 → 信源信用档 A–F（分档阈值自上而下首个命中）。"""
    for threshold, grade in CREDIT_GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "F"


def attribute_responsible_source(session: Session, item: IntelligenceItem) -> Source | None:
    """信用归因（decision-04）：责任信源 = 转引链上最早引入该陈述的信源。

    取 collected_at 最早的转引链节点（并列取最小 id）的信源；如实转述者不受奖惩。
    待确认信源不参与信用记账（decision-05），返回 None 由调用方跳过信用通路。
    """
    node = session.scalars(
        select(ProvenanceChainNode)
        .where(ProvenanceChainNode.item_id == item.id)
        .order_by(ProvenanceChainNode.collected_at.asc(), ProvenanceChainNode.id.asc())
        .limit(1)
    ).first()
    if node is None or node.source is None:
        return None
    if not node.source.confirmed:
        return None
    return node.source


def source_adjustments(session: Session, source_id: int) -> list[CreditAdjustment]:
    """信源的全部信用调整记录（按时间升序，可重放输入）。"""
    return list(
        session.scalars(
            select(CreditAdjustment)
            .where(CreditAdjustment.source_id == source_id)
            .order_by(CreditAdjustment.created_at.asc(), CreditAdjustment.id.asc())
        )
    )


@dataclass(frozen=True)
class CreditUpdateResult:
    """信用通路落账结果；责任信源不可归因时调用方不触发（结果为 None）。"""

    source_id: int
    delta: int
    score_after: float
    grade_after: str


def apply_credit_adjustment(
    *,
    source: Source,
    delta: int,
    occurred_at: datetime,
    feedback_id: int,
    session: Session,
) -> CreditUpdateResult:
    """落账一次信用调整：重放历史 + 本次奖惩 → 累计分 → 分档 → 更新 Source.credit。

    由 FeedbackRouter 在反馈落账事务内调用（提案即事务单元）。
    """
    history = source_adjustments(session, source.id)
    score = compute_credit_score(
        [(adj.delta, adj.created_at) for adj in history] + [(delta, occurred_at)],
        at=occurred_at,
    )
    grade = score_to_grade(score)

    adjustment = CreditAdjustment(
        source=source,
        feedback_id=feedback_id,
        delta=delta,
        score_after=score,
        grade_after=grade,
        formula_version=SOURCE_CREDIT_FORMULA_VERSION,
    )
    session.add(adjustment)
    source.credit = grade
    session.flush()
    return CreditUpdateResult(
        source_id=source.id, delta=delta, score_after=score, grade_after=grade
    )
