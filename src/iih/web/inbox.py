"""收件箱（首页）与条目详情页（doc-07 §3、§5，原型「收件箱/条目详情」页）。

浏览已核实情报 + 反馈入口（doc-07 §5）：收件箱行内一键（事实错误跳详情补理由）；
详情页六类型表单、理由可补写（事实错误必填）。分发匹配与推送后续里程碑加厚：
本页列表为已核实条目，不经分发记录。
"""

from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from iih.ledger.feedback_router import TYPE_LABELS, FeedbackRejectedError, FeedbackRouter
from iih.ledger.models import (
    Feedback,
    FeedbackType,
    IntelligenceItem,
    ItemStatus,
    VerificationRecord,
)
from iih.web.deps import get_session

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=TEMPLATES_DIR)

router = APIRouter()

STATUS_LABELS = {
    ItemStatus.LEAD: "线索",
    ItemStatus.CANDIDATE: "候选",
    ItemStatus.VERIFIED: "已核实",
    ItemStatus.UNDETERMINED: "存疑",
    ItemStatus.NOISE: "噪音",
    ItemStatus.REJECTED: "否决",
}


def _verified_items(session: Session) -> list[IntelligenceItem]:
    return list(
        session.scalars(
            select(IntelligenceItem)
            .where(IntelligenceItem.status == ItemStatus.VERIFIED)
            .order_by(IntelligenceItem.created_at.desc(), IntelligenceItem.id.desc())
        )
    )


def _render_item_detail(
    request: Request,
    session: Session,
    item_id: int,
    *,
    errors: list[str] | None = None,
    form_type: str | None = None,
    form_reason: str | None = None,
):
    item = session.get(IntelligenceItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="条目不存在")

    verification = session.scalars(
        select(VerificationRecord)
        .where(VerificationRecord.item_id == item_id)
        .order_by(VerificationRecord.created_at.desc(), VerificationRecord.id.desc())
        .limit(1)
    ).first()
    feedbacks = list(
        session.scalars(
            select(Feedback)
            .where(Feedback.item_id == item_id)
            .order_by(Feedback.created_at.desc(), Feedback.id.desc())
        )
    )

    return templates.TemplateResponse(
        request,
        "item_detail.html",
        {
            "item": item,
            "verification": verification,
            "feedbacks": feedbacks,
            "feedback_type_options": list(TYPE_LABELS.items()),
            "feedback_type_labels": TYPE_LABELS,
            "status_labels": STATUS_LABELS,
            "errors": errors or [],
            "form_type": form_type or "",
            "form_reason": form_reason or "",
        },
    )


@router.get("/")
def inbox_page(request: Request, session: Session = Depends(get_session)):
    return templates.TemplateResponse(
        request,
        "inbox.html",
        {"items": _verified_items(session), "status_labels": STATUS_LABELS},
    )


@router.get("/items/{item_id}")
def item_detail_page(item_id: int, request: Request, session: Session = Depends(get_session)):
    return _render_item_detail(request, session, item_id)


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
        return _render_item_detail(
            request,
            session,
            item_id,
            errors=[f"未知反馈类型：{feedback_type}"],
            form_type=feedback_type,
            form_reason=reason,
        )

    try:
        FeedbackRouter().submit(
            item_id=item_id, feedback_type=type_enum, reason=reason, session=session
        )
    except FeedbackRejectedError as exc:
        return _render_item_detail(
            request,
            session,
            item_id,
            errors=exc.reasons,
            form_type=feedback_type,
            form_reason=reason,
        )

    referer = request.headers.get("referer")
    return RedirectResponse(referer or f"/items/{item_id}", status_code=303)
