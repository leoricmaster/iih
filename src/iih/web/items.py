"""情报条目列表与详情（doc-07 §3）。

对象一页制：列表（默认待反馈 = 已核实 ∧ 未作废 ∧ 无反馈；状态 / 处置 / 反馈 / 采集模式可滤 + 检索）
+ 详情（摘要优先 + 状态自适应主区 + 核查深区折叠，反馈入口一步可达）。
"""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from iih.agents.verifier import Verifier
from iih.config import get_settings
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
from iih.tools.snapshot_store import SnapshotStore, make_snapshot_store
from iih.web.context import (
    REJECTION_REASON_LABELS,
    STATUS_LABELS,
    base_context,
    register_template_filters,
)
from iih.web.deps import get_session

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = register_template_filters(Jinja2Templates(directory=TEMPLATES_DIR))

router = APIRouter()

STATUS_KEYS = {
    "verified": ItemStatus.VERIFIED,
    "undetermined": ItemStatus.UNDETERMINED,
    "noise": ItemStatus.NOISE,
    "rejected": ItemStatus.REJECTED,
    "lead": ItemStatus.LEAD,
    "candidate": ItemStatus.CANDIDATE,
}

STATUS_FILTERS = [("all", "全部")] + [(k, STATUS_LABELS[s]) for k, s in STATUS_KEYS.items()]

# 处置是独立维度（doc-02 §4：作废为标记位非状态），不与状态复合
DISPOSITION_FILTERS = [
    ("all", "全部"),
    ("active", "未作废"),
    ("retracted", "已作废"),
]

# 待反馈 = 已核实 ∧ 未作废 ∧ 无反馈（原收件箱口径，doc-02 §4.3 分发以反馈闭环）
FEEDBACK_FILTERS = [
    ("all", "全部"),
    ("pending", "待反馈"),
    ("given", "已反馈"),
]

MODE_FILTERS = [
    ("all", "全部"),
    ("automated", "自动拉取"),
    ("manual", "人工提交"),
]


def _filter_items(
    session: Session, status: str, disposition: str, feedback: str, mode: str, q: str
) -> list[IntelligenceItem]:
    query = select(IntelligenceItem)
    match feedback:
        case "pending":
            query = query.where(
                IntelligenceItem.status == ItemStatus.VERIFIED,
                IntelligenceItem.retracted.is_(False),
                ~IntelligenceItem.feedbacks.any(),
            )
        case "given":
            query = query.where(IntelligenceItem.feedbacks.any())
    if status in STATUS_KEYS:
        query = query.where(IntelligenceItem.status == STATUS_KEYS[status])
    match disposition:
        case "active":
            query = query.where(IntelligenceItem.retracted.is_(False))
        case "retracted":
            query = query.where(IntelligenceItem.retracted.is_(True))
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
    status: str = "all",
    disposition: str = "all",
    feedback: str = "pending",
    mode: str = "all",
    q: str = "",
    flash: str = "",
    session: Session = Depends(get_session),
):
    items = _filter_items(session, status, disposition, feedback, mode, q)
    # 行内快捷反馈仅对待反馈条目开放（IIH-01.14 AC#4）：已核实 ∧ 未作废 ∧ 无反馈
    given_ids = set(
        session.scalars(
            select(Feedback.item_id).where(Feedback.item_id.in_([item.id for item in items]))
        )
    )
    quick_ids = {
        item.id
        for item in items
        if item.status is ItemStatus.VERIFIED and not item.retracted and item.id not in given_ids
    }
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
            "quick_ids": quick_ids,
            "status_labels": STATUS_LABELS,
            "status_filters": STATUS_FILTERS,
            "disposition_filters": DISPOSITION_FILTERS,
            "feedback_filters": FEEDBACK_FILTERS,
            "mode_filters": MODE_FILTERS,
            "cur_status": status if any(k == status for k, _ in STATUS_FILTERS) else "all",
            "cur_disposition": (
                disposition if any(k == disposition for k, _ in DISPOSITION_FILTERS) else "all"
            ),
            "cur_feedback": (
                feedback if any(k == feedback for k, _ in FEEDBACK_FILTERS) else "pending"
            ),
            "cur_mode": mode if any(k == mode for k, _ in MODE_FILTERS) else "all",
            "cur_q": q.strip(),
            "flash": flash,
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
    item: IntelligenceItem,
    reviews: list[ReviewDecision],
    verifications: list[VerificationRecord],
    feedbacks: list[Feedback],
) -> list[tuple[str, object]]:
    """状态迁移轨迹（原型 trail）：按决策时间升序走全部审查与核实记录。

    审查序列可呈现异议重审往返（噪音 → 候选 / 噪音维持）；核实序列可呈现存疑重核
    （存疑 → 已核实）；作废以事实错误反馈时间收尾。
    """
    trail: list[tuple[str, object]] = [
        (f"线索（{'人工提交' if item.mode is ItemMode.MANUAL else '自动拉取'}）", item.created_at)
    ]
    for index, review in enumerate(reviews):
        reason = (
            REJECTION_REASON_LABELS.get(review.reason_type, "未知")
            if review.reason_type
            else "未知"
        )
        if review.decision.value == "pass":
            label = "候选情报（异议重审通过）" if index > 0 else "候选情报（审查通过）"
        else:
            label = (
                f"噪音（异议重审维持 · {reason}）" if index > 0 else f"噪音（审查否决 · {reason}）"
            )
        trail.append((label, review.created_at))
    for v in verifications:
        if v.outcome.value == "verified":
            trail.append((f"已核实（{v.rating}）", v.created_at))
        else:
            trail.append(("存疑（核实无法完成）", v.created_at))
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
    flash: str = "",
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
    reviews = list(
        session.scalars(
            select(ReviewDecision)
            .where(ReviewDecision.item_id == item_id)
            .order_by(ReviewDecision.created_at.asc(), ReviewDecision.id.asc())
        )
    )
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
            "review": reviews[-1] if reviews else None,
            "chain_nodes": chain_nodes,
            "attribution_source_id": chain_nodes[0].source_id if chain_nodes else None,
            "prev_id": prev_id,
            "next_id": next_id,
            "trail": _item_trail(item, reviews, list(reversed(verifications)), feedbacks),
            "type_labels": TYPE_LABELS,
            "status_labels": STATUS_LABELS,
            "reason_labels": REJECTION_REASON_LABELS,
            "err": err,
            "flash": flash,
            "fb_type": fb_type,
            "fb_reason": fb_reason,
        },
    )


@router.get("/items/{item_id}/snapshot")
def item_snapshot(item_id: int, request: Request, session: Session = Depends(get_session)):
    """快照回放：对象存储原始 HTML 原样返回（新窗口查看）。

    沙箱响应头：存档页里的脚本 / 表单不得在本站源下执行（CSP sandbox）。
    """
    item = session.get(IntelligenceItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="条目不存在")
    if not item.snapshot_object_key:
        raise HTTPException(status_code=404, detail="该条目无对象快照")

    store: SnapshotStore = getattr(request.app.state, "snapshot_store", None) or (
        make_snapshot_store(get_settings())
    )
    request.app.state.snapshot_store = store
    return Response(
        content=store.get_html(item.snapshot_object_key),
        media_type="text/html; charset=utf-8",
        headers={"Content-Security-Policy": "sandbox", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/items/{item_id}")
def item_detail_page(
    item_id: int,
    request: Request,
    err: str = "",
    flash: str = "",
    fb_type: str = "",
    fb_reason: str = "",
    session: Session = Depends(get_session),
):
    return _render_detail(
        request, session, item_id, err=err, flash=flash, fb_type=fb_type, fb_reason=fb_reason
    )


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
