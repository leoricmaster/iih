"""收件箱（首页）与反馈提交（doc-07 §3、§5，原型「收件箱」页）。

三类待办聚合：待反馈条目 · 警报汇总 · 待确认信源（decision-05）。
本里程碑分发记录与警报未建：待反馈以已核实未作废条目近似、警报区块空态呈现；
待确认信源为素材归因补记产生（decision-05 通道二），确认动作后续里程碑开通。
"""

from pathlib import Path
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from iih.ledger.feedback_router import TYPE_LABELS, FeedbackRejectedError, FeedbackRouter
from iih.ledger.models import (
    FeedbackType,
    IntelligenceItem,
    ItemStatus,
    Source,
    VerificationRecord,
)
from iih.web.context import STATUS_LABELS, base_context
from iih.web.deps import get_session

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=TEMPLATES_DIR)

router = APIRouter()

QUICK_TYPES = [
    FeedbackType.VALID,
    FeedbackType.DUPLICATE_NOISE,
    FeedbackType.IRRELEVANT,
    FeedbackType.OUTDATED,
    FeedbackType.RATING_DISPUTE,
]


def _feedback_items(session: Session) -> list[IntelligenceItem]:
    """待反馈条目：已核实未作废（分发记录未建的近似，doc-07 §3）。"""
    return list(
        session.scalars(
            select(IntelligenceItem)
            .where(IntelligenceItem.status == ItemStatus.VERIFIED)
            .where(IntelligenceItem.retracted.is_(False))
            .order_by(IntelligenceItem.created_at.desc(), IntelligenceItem.id.desc())
        )
    )


def _latest_verifications(session: Session, item_ids: list[int]) -> dict[int, VerificationRecord]:
    """各条目最新核实记录（独立信源计数 N 与评级依据来源）。"""
    result: dict[int, VerificationRecord] = {}
    for item_id in item_ids:
        record = session.scalars(
            select(VerificationRecord)
            .where(VerificationRecord.item_id == item_id)
            .order_by(VerificationRecord.created_at.desc(), VerificationRecord.id.desc())
            .limit(1)
        ).first()
        if record is not None:
            result[item_id] = record
    return result


def _pending_sources(session: Session) -> list[Source]:
    """待确认信源：素材归因补记产生，不入正式池（decision-05 通道二）。"""
    return list(session.scalars(select(Source).where(Source.confirmed.is_(False))))


def _undetermined_count(session: Session) -> int:
    """待复核（存疑）条目计数：运行结果不在待反馈队列，需显式指向防「结果消失」。"""
    return (
        session.scalar(
            select(func.count())
            .select_from(IntelligenceItem)
            .where(IntelligenceItem.status == ItemStatus.UNDETERMINED)
        )
        or 0
    )


@router.get("/")
def inbox_page(request: Request, flash: str = "", session: Session = Depends(get_session)):
    items = _feedback_items(session)
    return templates.TemplateResponse(
        request,
        "inbox.html",
        {
            **base_context(session, "inbox"),
            "items": items,
            "verifications": _latest_verifications(session, [i.id for i in items]),
            "undetermined_count": _undetermined_count(session),
            "pending_sources": _pending_sources(session),
            "quick_types": QUICK_TYPES,
            "type_labels": TYPE_LABELS,
            "status_labels": STATUS_LABELS,
            "flash": flash,
        },
    )


@router.post("/items/{item_id}/feedback")
def item_feedback(
    item_id: int,
    request: Request,
    feedback_type: str = Form(""),
    reason: str = Form(""),
    session: Session = Depends(get_session),
):
    """反馈提交：反馈路由校验落账并分流（doc-02 §6）；失败回详情页带错误，成功回来源页。"""
    if session.get(IntelligenceItem, item_id) is None:
        raise HTTPException(status_code=404, detail="条目不存在")

    try:
        type_enum = FeedbackType(feedback_type)
    except ValueError:
        return RedirectResponse(
            f"/items/{item_id}?err={quote_plus(f'未知反馈类型：{feedback_type}')}"
            f"&fb_type={quote_plus(feedback_type)}&fb_reason={quote_plus(reason)}",
            status_code=303,
        )

    try:
        FeedbackRouter().submit(
            item_id=item_id, feedback_type=type_enum, reason=reason, session=session
        )
    except FeedbackRejectedError as exc:
        return RedirectResponse(
            f"/items/{item_id}?err={quote_plus('；'.join(exc.reasons))}"
            f"&fb_type={quote_plus(feedback_type)}&fb_reason={quote_plus(reason)}",
            status_code=303,
        )

    referer = request.headers.get("referer")
    return RedirectResponse(referer or f"/items/{item_id}", status_code=303)
