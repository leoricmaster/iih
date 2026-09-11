"""录入素材页（doc-07 §2.3、原型）：选媒介、填陈述，提交落账为线索。"""

from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from instructor import Instructor
from sqlalchemy import select
from sqlalchemy.orm import Session

from iih.agents.collector import Collector
from iih.config import get_settings
from iih.ledger.models import IntelligenceItem, ItemMode, ItemStatus, Medium
from iih.ledger.state_machine import ProposalRejectedError, StateMachineExecutor
from iih.web.deps import get_llm_client, get_session

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

RECENT_LIMIT = 10


def _offline_mediums(session: Session) -> list[Medium]:
    """媒介下拉封闭集合；互联网为自动拉取、不经本页（doc-07 §2.3）。"""
    return list(
        session.scalars(select(Medium).where(Medium.code != "internet").order_by(Medium.id))
    )


def _recent_manual_items(session: Session) -> list[IntelligenceItem]:
    return list(
        session.scalars(
            select(IntelligenceItem)
            .where(IntelligenceItem.mode == ItemMode.MANUAL)
            .order_by(IntelligenceItem.created_at.desc(), IntelligenceItem.id.desc())
            .limit(RECENT_LIMIT)
        )
    )


def _render(request: Request, session: Session, errors: list[str] | None = None):
    return templates.TemplateResponse(
        request,
        "submissions.html",
        {
            "mediums": _offline_mediums(session),
            "items": _recent_manual_items(session),
            "status_labels": STATUS_LABELS,
            "errors": errors or [],
        },
    )


@router.get("/submissions")
def submissions_page(request: Request, session: Session = Depends(get_session)):
    return _render(request, session)


@router.post("/submissions")
def submit(
    request: Request,
    medium_code: str = Form(""),
    statement: str = Form(""),
    session: Session = Depends(get_session),
    llm: Instructor = Depends(get_llm_client),
):
    """表单校验 → Collector 归因 → 状态机执行器落账 Lead。"""
    errors: list[str] = []
    if not medium_code:
        errors.append("请选择媒介")
    if not statement.strip():
        errors.append("请填写陈述内容")
    if not errors and medium_code == "internet":
        errors.append("互联网媒介为自动拉取，不经本页录入")

    if errors:
        return _render(request, session, errors)

    collector = Collector(llm=llm, session=session, model=get_settings().llm_model)
    proposal = collector.submit_manual(medium_code=medium_code, statement=statement.strip())
    try:
        StateMachineExecutor().execute(proposal, session=session)
    except ProposalRejectedError as exc:
        return _render(request, session, exc.reasons)

    return RedirectResponse("/submissions", status_code=303)
