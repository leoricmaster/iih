"""信源库页（doc-07 §2.1、§3，原型「信源库」页）：登记种子信源 + 首条互联网途径，列表浏览。"""

from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from iih.ledger.models import Source, SourceType
from iih.ledger.proposal import SourceRegisterPayload, SourceRegisterProposal
from iih.ledger.state_machine import ProposalRejectedError, StateMachineExecutor
from iih.web.deps import get_session

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=TEMPLATES_DIR)

router = APIRouter()

SOURCE_TYPE_LABELS = {
    SourceType.COMPANY: "公司",
    SourceType.GOVERNMENT: "政府",
    SourceType.ORGANIZATION: "组织",
    SourceType.MEDIA: "媒体",
    SourceType.PERSON: "人物",
    SourceType.OTHER: "其他",
}

REGISTER_RATIONALE = "人工登记（decision-05 通道一）"


def _confirmed_sources(session: Session) -> list[Source]:
    """已确认信源列表，途径经关系加载（doc-03 §六：主体/途径两栏）。"""
    return list(
        session.scalars(select(Source).where(Source.confirmed.is_(True)).order_by(Source.id))
    )


def _render(request: Request, session: Session, errors: list[str] | None = None):
    return templates.TemplateResponse(
        request,
        "sources.html",
        {
            "sources": _confirmed_sources(session),
            "source_types": list(SOURCE_TYPE_LABELS.items()),
            "source_type_labels": SOURCE_TYPE_LABELS,
            "errors": errors or [],
        },
    )


@router.get("/sources")
def sources_page(request: Request, session: Session = Depends(get_session)):
    return _render(request, session)


@router.post("/sources")
def register(
    request: Request,
    source_name: str = Form(""),
    source_type: str = Form(""),
    outlet_name: str = Form(""),
    outlet_entry: str = Form(""),
    session: Session = Depends(get_session),
):
    """表单校验 → 种子信源登记提案 → 状态机执行器落账。"""
    errors: list[str] = []
    if not source_name.strip():
        errors.append("请填写主体名称")
    if not source_type:
        errors.append("请选择类型")
    if not outlet_name.strip():
        errors.append("请填写途径名")
    if not outlet_entry.strip():
        errors.append("请填写采集入口")

    if errors:
        return _render(request, session, errors)

    try:
        source_type_enum = SourceType(source_type)
    except ValueError:
        return _render(request, session, [f"未知信源类型：{source_type}"])

    proposal = SourceRegisterProposal(
        payload=SourceRegisterPayload(
            source_name=source_name.strip(),
            source_type=source_type_enum,
            outlet_name=outlet_name.strip(),
            outlet_entry=outlet_entry.strip(),
        ),
        rationale=REGISTER_RATIONALE,
    )
    try:
        StateMachineExecutor().execute(proposal, session=session)
    except ProposalRejectedError as exc:
        return _render(request, session, exc.reasons)

    return RedirectResponse("/sources", status_code=303)
