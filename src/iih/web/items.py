"""情报条目列表与详情（doc-07 §3，原型「情报条目」页）。

对象一页制：列表（已核实起全状态可滤 + 采集模式 + 检索）+ 详情
（摘要优先 + 状态自适应主区 + 核查深区折叠，doc-07 §3）。
"""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from iih.agents.verifier import Verifier
from iih.ledger.feedback_router import TYPE_LABELS
from iih.ledger.models import (
    Feedback,
    FeedbackType,
    IntelligenceItem,
    ItemMode,
    ItemStatus,
    ProvenanceChainNode,
    ReviewDecision,
    Source,
    VerificationRecord,
)
from iih.ledger.proposal import ItemReverifyPayload, ItemReverifyProposal
from iih.ledger.state_machine import ProposalRejectedError, StateMachineExecutor
from iih.web.context import STATUS_LABELS, base_context
from iih.web.deps import get_session

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=TEMPLATES_DIR)

router = APIRouter()

# 已核实起 = 审查迁移之后的所有状态（doc-07 §3：线索/候选不入默认视图）
VERIFIED_UP_STATUSES = (
    ItemStatus.VERIFIED,
    ItemStatus.UNDETERMINED,
    ItemStatus.NOISE,
    ItemStatus.REJECTED,
)

STATUS_FILTERS = [
    ("verified_up", "已核实起"),
    ("lead", "线索"),
    ("candidate", "候选"),
    ("undetermined", "存疑"),
    ("retracted", "作废"),
    ("all", "全部状态"),
]

MODE_FILTERS = [
    ("all", "全部"),
    ("automated", "自动拉取"),
    ("manual", "人工提交"),
]


def _filter_items(session: Session, status: str, mode: str, q: str) -> list[IntelligenceItem]:
    query = select(IntelligenceItem)
    match status:
        case "verified_up":
            query = query.where(IntelligenceItem.status.in_(VERIFIED_UP_STATUSES))
        case "lead":
            query = query.where(IntelligenceItem.status == ItemStatus.LEAD)
        case "candidate":
            query = query.where(IntelligenceItem.status == ItemStatus.CANDIDATE)
        case "undetermined":
            query = query.where(IntelligenceItem.status == ItemStatus.UNDETERMINED)
        case "retracted":
            query = query.where(IntelligenceItem.retracted.is_(True))
        case _:
            pass  # all
    match mode:
        case "automated":
            query = query.where(IntelligenceItem.mode == ItemMode.AUTOMATED)
        case "manual":
            query = query.where(IntelligenceItem.mode == ItemMode.MANUAL)
    if q.strip():
        like = f"%{q.strip()}%"
        query = query.where(
            or_(
                IntelligenceItem.statement.ilike(like),
                IntelligenceItem.source.has(Source.name.ilike(like)),
            )
        )
    return list(
        session.scalars(
            query.order_by(IntelligenceItem.created_at.desc(), IntelligenceItem.id.desc())
        )
    )


def _latest_verification(session: Session, item_id: int) -> VerificationRecord | None:
    return session.scalars(
        select(VerificationRecord)
        .where(VerificationRecord.item_id == item_id)
        .order_by(VerificationRecord.created_at.desc(), VerificationRecord.id.desc())
        .limit(1)
    ).first()


@router.get("/items")
def items_page(
    request: Request,
    status: str = "verified_up",
    mode: str = "all",
    q: str = "",
    session: Session = Depends(get_session),
):
    items = _filter_items(session, status, mode, q)
    verifications = {
        item.id: _latest_verification(session, item.id)
        for item in items
        if item.status in (ItemStatus.VERIFIED, ItemStatus.UNDETERMINED)
    }
    return templates.TemplateResponse(
        request,
        "items.html",
        {
            **base_context(session, "items"),
            "items": items,
            "verifications": verifications,
            "status_labels": STATUS_LABELS,
            "status_filters": STATUS_FILTERS,
            "mode_filters": MODE_FILTERS,
            "cur_status": status if any(k == status for k, _ in STATUS_FILTERS) else "verified_up",
            "cur_mode": mode if any(k == mode for k, _ in MODE_FILTERS) else "all",
            "cur_q": q.strip(),
        },
    )


def _chain_nodes(session: Session, item_id: int) -> list[ProvenanceChainNode]:
    """转引链节点按采集时间升序（最早引入 = 信用归因对象 · decision-04）。"""
    return list(
        session.scalars(
            select(ProvenanceChainNode)
            .where(ProvenanceChainNode.item_id == item_id)
            .order_by(ProvenanceChainNode.collected_at.asc(), ProvenanceChainNode.id.asc())
        )
    )


def _neighbors(session: Session, item_id: int) -> tuple[int | None, int | None]:
    prev_id = session.scalar(
        select(func.max(IntelligenceItem.id)).where(IntelligenceItem.id < item_id)
    )
    next_id = session.scalar(
        select(func.min(IntelligenceItem.id)).where(IntelligenceItem.id > item_id)
    )
    return prev_id, next_id


def _item_trail(
    item: IntelligenceItem, review: ReviewDecision | None, feedbacks: list[Feedback]
) -> list[tuple[str, object]]:
    """状态迁移轨迹（原型 trail）：线索 → 审查 → 核实 → 作废。"""
    trail: list[tuple[str, object]] = [
        (f"线索（{'人工提交' if item.mode is ItemMode.MANUAL else '自动拉取'}）", item.created_at)
    ]
    if review is not None:
        if review.decision.value == "pass":
            trail.append(("候选情报（审查通过）", review.created_at))
        else:
            reason = review.reason_type.value if review.reason_type else "未知"
            trail.append((f"噪音（审查否决 · {reason}）", review.created_at))
    if item.rating or item.status is ItemStatus.UNDETERMINED:
        if item.rating:
            trail.append((f"已核实（{item.rating}）", item.updated_at))
        else:
            trail.append(("存疑（核实无法完成）", item.updated_at))
    if item.retracted:
        factual = next(
            (f for f in feedbacks if f.feedback_type is FeedbackType.FACTUAL_ERROR), None
        )
        trail.append(("作废（事实错误）", factual.created_at if factual else item.updated_at))
    return trail


def _render_detail(
    request: Request,
    session: Session,
    item_id: int,
    *,
    err: str = "",
    fb_type: str = "",
    fb_reason: str = "",
):
    item = session.get(IntelligenceItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="条目不存在")

    verifications = list(
        session.scalars(
            select(VerificationRecord)
            .where(VerificationRecord.item_id == item_id)
            .order_by(VerificationRecord.created_at.desc(), VerificationRecord.id.desc())
        )
    )
    feedbacks = list(
        session.scalars(
            select(Feedback)
            .where(Feedback.item_id == item_id)
            .order_by(Feedback.created_at.desc(), Feedback.id.desc())
        )
    )
    review = session.scalars(
        select(ReviewDecision)
        .where(ReviewDecision.item_id == item_id)
        .order_by(ReviewDecision.created_at.desc(), ReviewDecision.id.desc())
        .limit(1)
    ).first()
    prev_id, next_id = _neighbors(session, item_id)
    chain_nodes = _chain_nodes(session, item_id)

    return templates.TemplateResponse(
        request,
        "item_detail.html",
        {
            **base_context(session, "items"),
            "item": item,
            "verifications": verifications,
            "latest_verification": verifications[0] if verifications else None,
            "feedbacks": feedbacks,
            "review": review,
            "chain_nodes": chain_nodes,
            "attribution_source_id": chain_nodes[0].source_id if chain_nodes else None,
            "prev_id": prev_id,
            "next_id": next_id,
            "trail": _item_trail(item, review, feedbacks),
            "type_labels": TYPE_LABELS,
            "status_labels": STATUS_LABELS,
            "err": err,
            "fb_type": fb_type,
            "fb_reason": fb_reason,
        },
    )


@router.get("/items/{item_id}")
def item_detail_page(
    item_id: int,
    request: Request,
    err: str = "",
    fb_type: str = "",
    fb_reason: str = "",
    session: Session = Depends(get_session),
):
    return _render_detail(request, session, item_id, err=err, fb_type=fb_type, fb_reason=fb_reason)


@router.post("/items/{item_id}/reverify")
def item_reverify(item_id: int, request: Request, session: Session = Depends(get_session)):
    """存疑重核：Undetermined → Candidate（新证据回流，doc-02 §4.1）→ 立即确定性重评。

    核实不调 LLM（doc-06 §5），重评在请求内同步完成；评级结果进 VerificationRecord
    版本化历史（旧记录保留，可重放）。
    """
    item = session.get(IntelligenceItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="条目不存在")

    try:
        StateMachineExecutor().execute(
            ItemReverifyProposal(
                payload=ItemReverifyPayload(item_id=item_id),
                rationale="Web 人工重核（新证据回流，doc-02 §4.1）",
            ),
            session=session,
        )
        verification = Verifier(session=session).verify(item)
        StateMachineExecutor().execute(verification, session=session)
    except ProposalRejectedError as exc:
        return _render_detail(request, session, item_id, err="；".join(exc.reasons))
    return RedirectResponse(f"/items/{item_id}", status_code=303)
