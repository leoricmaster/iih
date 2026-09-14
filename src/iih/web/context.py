"""Web 层共享模板上下文：侧栏徽标计数与通用标签。"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from iih.config import get_settings
from iih.ledger.models import (
    IntelligenceItem,
    ItemStatus,
    RejectionReasonEnum,
)

STATUS_LABELS = {
    ItemStatus.LEAD: "线索",
    ItemStatus.CANDIDATE: "候选",
    ItemStatus.VERIFIED: "已核实",
    ItemStatus.UNDETERMINED: "存疑",
    ItemStatus.NOISE: "噪音",
    ItemStatus.REJECTED: "否决",
}

REJECTION_REASON_LABELS = {
    RejectionReasonEnum.IRRELEVANT: "不相关",
    RejectionReasonEnum.DUPLICATE: "重复",
    RejectionReasonEnum.INVALID: "无效",
}


def inbox_count(session: Session) -> int:
    """收件箱徽标：待反馈条目计数。

    分发记录未建（后续里程碑），以已核实未作废条目近似。
    """
    return (
        session.scalar(
            select(func.count(IntelligenceItem.id)).where(
                IntelligenceItem.status == ItemStatus.VERIFIED,
                IntelligenceItem.retracted.is_(False),
            )
        )
        or 0
    )


def base_context(session: Session, nav: str) -> dict:
    """全站壳所需上下文（base.html）。"""
    return {
        "nav": nav,
        "inbox_count": inbox_count(session),
        "pipeline_interval": get_settings().pipeline_interval_seconds,
    }
