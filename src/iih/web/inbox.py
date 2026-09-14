"""收件箱（首页）与条目详情页（doc-07 §3、原型「收件箱/条目详情」页）：浏览已核实情报。

分发匹配与推送后续里程碑加厚：本页列表为已核实条目，不经分发记录。
"""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from iih.ledger.models import IntelligenceItem, ItemStatus, VerificationRecord
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


@router.get("/")
def inbox_page(request: Request, session: Session = Depends(get_session)):
    return templates.TemplateResponse(
        request,
        "inbox.html",
        {"items": _verified_items(session), "status_labels": STATUS_LABELS},
    )


@router.get("/items/{item_id}")
def item_detail_page(item_id: int, request: Request, session: Session = Depends(get_session)):
    item = session.get(IntelligenceItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="条目不存在")

    verification = session.scalars(
        select(VerificationRecord)
        .where(VerificationRecord.item_id == item_id)
        .order_by(VerificationRecord.created_at.desc(), VerificationRecord.id.desc())
        .limit(1)
    ).first()

    return templates.TemplateResponse(
        request,
        "item_detail.html",
        {
            "item": item,
            "verification": verification,
            "status_labels": STATUS_LABELS,
        },
    )
