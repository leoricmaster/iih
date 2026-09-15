"""录入素材页（doc-07 §2.3、原型）：选媒介、贴文字纪要，抽取陈述落账为线索。"""

from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.templating import Jinja2Templates
from instructor import Instructor
from sqlalchemy import select
from sqlalchemy.orm import Session

from iih.agents.collector import Collector
from iih.config import get_settings
from iih.ledger.models import IntelligenceItem, ItemMode, Medium
from iih.ledger.state_machine import ProposalRejectedError, StateMachineExecutor
from iih.web.context import STATUS_LABELS, base_context, register_template_filters
from iih.web.deps import get_llm_client, get_session
from iih.web.flash import redirect_with_flash

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = register_template_filters(Jinja2Templates(directory=TEMPLATES_DIR))

router = APIRouter()

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


def _render(
    request: Request,
    session: Session,
    errors: list[str] | None = None,
    flash: str = "",
    form_medium: str = "",
    form_statement: str = "",
):
    return templates.TemplateResponse(
        request,
        "submissions.html",
        {
            **base_context(session, "submit"),
            "mediums": _offline_mediums(session),
            "items": _recent_manual_items(session),
            "status_labels": STATUS_LABELS,
            "errors": errors or [],
            "flash": flash,
            "form_medium": form_medium,
            "form_statement": form_statement,
        },
    )


@router.get("/submissions")
def submissions_page(request: Request, flash: str = "", session: Session = Depends(get_session)):
    return _render(request, session, flash=flash)


@router.post("/submissions")
def submit(
    request: Request,
    medium_code: str = Form(""),
    statement: str = Form(""),
    session: Session = Depends(get_session),
    llm: Instructor = Depends(get_llm_client),
):
    """表单校验 → Collector 抽取 + 归因 → 逐条落账 Lead。"""

    def fail(reasons: list[str]):
        return _render(request, session, reasons, form_medium=medium_code, form_statement=statement)

    errors: list[str] = []
    if not medium_code:
        errors.append("请选择媒介")
    if not statement.strip():
        errors.append("请填写纪要内容")
    if not errors and medium_code == "internet":
        errors.append("互联网媒介为自动拉取，不经本页录入")

    if errors:
        return fail(errors)

    collector = Collector(llm=llm, session=session, model=get_settings().llm_model)
    try:
        proposals = collector.submit_manual(medium_code=medium_code, statement=statement.strip())
    except ValueError as exc:
        return fail([str(exc)])
    if not proposals:
        return fail(["未能从提交文本中识别出情报陈述"])

    created = 0
    failed = 0
    reject_reasons: list[str] = []
    for proposal in proposals:
        try:
            StateMachineExecutor().execute(proposal, session=session)
            created += 1
        except ProposalRejectedError as exc:
            failed += 1
            reject_reasons.extend(exc.reasons)
    if not created:
        return fail(reject_reasons or ["落账失败"])

    message = f"已提交：抽取陈述 {created} 条，进入流水线"
    if failed:
        message += f"；{failed} 条落账失败"
    return redirect_with_flash("/submissions", message)
