"""信源库页（doc-07 §2.1、§3，原型「信源库/信源画像」页）。

列表（主体 / 途径两栏）+ 登记种子信源 + 信源画像（信用档与调整历史、途径、参与条目）。
"""

from pathlib import Path
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from iih.ledger.credit import HALF_LIFE_DAYS
from iih.ledger.models import (
    CreditAdjustment,
    IntelligenceItem,
    ProvenanceChainNode,
    Source,
    SourceAlias,
    SourceType,
)
from iih.ledger.proposal import (
    SourceConfirmPayload,
    SourceConfirmProposal,
    SourceRegisterPayload,
    SourceRegisterProposal,
    SourceRejectPayload,
    SourceRejectProposal,
)
from iih.ledger.state_machine import ProposalRejectedError, StateMachineExecutor
from iih.web.context import (
    SOURCE_TYPE_LABELS,
    STATUS_LABELS,
    base_context,
    register_template_filters,
)
from iih.web.deps import get_session
from iih.web.flash import redirect_with_flash

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = register_template_filters(Jinja2Templates(directory=TEMPLATES_DIR))

router = APIRouter()

REGISTER_RATIONALE = "人工登记（decision-05 通道一）"
CONFIRM_RATIONALE = "人工确认（decision-05 准入把关）"
REJECT_RATIONALE = "人工拒绝（decision-05 准入把关）"


def _safe_next(next_url: str) -> str:
    """回跳白名单：仅站内路径（/ 开头且非 //），防开放重定向。"""
    stripped = next_url.strip()
    return stripped if stripped.startswith("/") and not stripped.startswith("//") else "/sources"


def _confirmed_sources(session: Session) -> list[Source]:
    """已确认信源列表，途径经关系加载（doc-03 §六：主体/途径两栏）。"""
    return list(
        session.scalars(select(Source).where(Source.confirmed.is_(True)).order_by(Source.id))
    )


def _pending_sources(session: Session) -> list[Source]:
    """待确认信源（decision-05 通道二）：拒绝即出队，再归因命中时重捞（rejected_at 清空）。"""
    return list(
        session.scalars(
            select(Source)
            .where(Source.confirmed.is_(False), Source.rejected_at.is_(None))
            .order_by(Source.id)
        )
    )


def _feedback_counts(session: Session) -> dict[int, dict[str, int]]:
    """各信源信用通路反馈计数（按调整记录 delta 符号归并）。"""
    rows = session.execute(
        select(
            CreditAdjustment.source_id,
            func.count().filter(CreditAdjustment.delta > 0),
            func.count().filter(CreditAdjustment.delta < 0),
        ).group_by(CreditAdjustment.source_id)
    ).all()
    return {
        source_id: {"valid": valid or 0, "factual_error": factual or 0}
        for source_id, valid, factual in rows
    }


def _render(
    request: Request,
    session: Session,
    errors: list[str] | None = None,
    flash: str = "",
    err: str = "",
):
    return templates.TemplateResponse(
        request,
        "sources.html",
        {
            **base_context(session, "sources"),
            "sources": _confirmed_sources(session),
            "pending_sources": _pending_sources(session),
            "feedback_counts": _feedback_counts(session),
            "source_types": list(SOURCE_TYPE_LABELS.items()),
            "source_type_labels": SOURCE_TYPE_LABELS,
            "errors": errors or [],
            "flash": flash,
            "err": err,
        },
    )


@router.get("/sources")
def sources_page(
    request: Request, flash: str = "", err: str = "", session: Session = Depends(get_session)
):
    return _render(request, session, flash=flash, err=err)


@router.post("/sources")
def register(
    request: Request,
    source_name: str = Form(""),
    source_type: str = Form(""),
    outlet_name: str = Form(""),
    outlet_entry: str = Form(""),
    initial_credit: str = Form(""),
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
    credit = initial_credit.strip()
    if not credit:
        errors.append("请选择初始信用档")
    elif credit not in "ABCDEF":
        errors.append("初始信用档需为 A–F")

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
            initial_credit=credit or None,
        ),
        rationale=REGISTER_RATIONALE,
    )
    try:
        StateMachineExecutor().execute(proposal, session=session)
    except ProposalRejectedError as exc:
        return _render(request, session, exc.reasons)

    return RedirectResponse("/sources", status_code=303)


@router.get("/sources/{source_id}")
def source_detail(
    source_id: int,
    request: Request,
    err: str = "",
    flash: str = "",
    session: Session = Depends(get_session),
):
    """信源画像：信用（档 + 调整历史）+ 途径 + 参与条目（转引链出现即计）。"""
    source = session.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="信源不存在")

    adjustments = list(
        session.scalars(
            select(CreditAdjustment)
            .where(CreditAdjustment.source_id == source_id)
            .order_by(CreditAdjustment.created_at.desc(), CreditAdjustment.id.desc())
        )
    )
    participating = list(
        session.scalars(
            select(IntelligenceItem)
            .where(
                IntelligenceItem.id.in_(
                    select(ProvenanceChainNode.item_id).where(
                        ProvenanceChainNode.source_id == source_id
                    )
                )
            )
            .order_by(IntelligenceItem.created_at.desc(), IntelligenceItem.id.desc())
        )
    )
    return templates.TemplateResponse(
        request,
        "source_detail.html",
        {
            **base_context(session, "sources"),
            "source": source,
            "adjustments": adjustments,
            "participating": participating,
            "source_types": list(SOURCE_TYPE_LABELS.items()),
            "source_type_labels": SOURCE_TYPE_LABELS,
            "item_status_labels": STATUS_LABELS,
            "half_life_days": HALF_LIFE_DAYS,
            "err": err,
            "flash": flash,
        },
    )


@router.post("/sources/{source_id}/rename")
def source_rename(
    source_id: int,
    request: Request,
    name: str = Form(""),
    session: Session = Depends(get_session),
):
    """主体改名（消费方配置编辑，同信用档人工编辑）；同名冲突拦截。"""
    source = session.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="信源不存在")

    new_name = name.strip()
    if not source.confirmed:
        err = "待确认信源不入库、不建画像、不记账"
    elif not new_name:
        err = "名称不能为空"
    else:
        dup = session.scalars(
            select(Source).where(Source.name == new_name, Source.id != source_id)
        ).first()
        alias = session.scalars(select(SourceAlias).where(SourceAlias.name == new_name)).first()
        if dup is not None:
            err = f"已存在同名信源：{new_name}"
        elif alias is not None:
            err = f"已存在同名别名（归属 {alias.source.name}）：{new_name}"
        else:
            if new_name != source.name:
                session.add(SourceAlias(source=source, name=source.name))
            source.name = new_name
            session.commit()
            return redirect_with_flash(f"/sources/{source_id}", f"已改名：{new_name}")
    return RedirectResponse(f"/sources/{source_id}?err={quote_plus(err)}", status_code=303)


@router.post("/sources/{source_id}/credit")
def source_credit_set(
    source_id: int,
    request: Request,
    credit: str = Form(""),
    session: Session = Depends(get_session),
):
    """人工补设/调整信用档（doc-04 §2.3：人工设档直接生效；A–F 或清空）。

    消费方配置编辑，非智能体写入；调整历史（信用通路反馈）不受影响。
    """
    source = session.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="信源不存在")

    grade = credit.strip()
    if not source.confirmed:
        err = "待确认信源不入库、不建画像、不记账"
    elif grade and grade not in "ABCDEF":
        err = f"信用档需为 A–F 或不设：{grade}"
    else:
        source.credit = grade or None
        session.commit()
        return redirect_with_flash(f"/sources/{source_id}", "信用档已保存")
    return RedirectResponse(f"/sources/{source_id}?err={quote_plus(err)}", status_code=303)


@router.post("/sources/{source_id}/confirm")
def source_confirm(
    source_id: int,
    request: Request,
    initial_credit: str = Form(""),
    name: str = Form(""),
    source_type: str = Form(""),
    next_url: str = Form("", alias="next"),
    session: Session = Depends(get_session),
):
    """待确认信源确认入池（IIH-05.01）：可修正名/类型 + 初始档 → 提案落账。"""
    target = _safe_next(next_url)
    try:
        type_enum = SourceType(source_type) if source_type else None
    except ValueError:
        return redirect_with_flash(target, f"未知信源类型：{source_type}", param="err")
    try:
        result = StateMachineExecutor().execute(
            SourceConfirmProposal(
                payload=SourceConfirmPayload(
                    source_id=source_id,
                    initial_credit=initial_credit.strip(),
                    name=name.strip() or None,
                    source_type=type_enum,
                ),
                rationale=CONFIRM_RATIONALE,
            ),
            session=session,
        )
    except ProposalRejectedError as exc:
        return redirect_with_flash(target, "；".join(exc.reasons), param="err")
    source = session.get(Source, result.source_id or source_id)
    final_name = source.name if source else str(source_id)
    if source is not None and source.id != source_id:
        return redirect_with_flash(target, f"已并入既有信源：{final_name}")
    return redirect_with_flash(target, f"已确认入信源库：{final_name}")


@router.post("/sources/{source_id}/reject")
def source_reject(
    source_id: int,
    request: Request,
    next_url: str = Form("", alias="next"),
    session: Session = Depends(get_session),
):
    """待确认信源拒绝（IIH-05.01）：不入池、留痕，条目不受影响。"""
    target = _safe_next(next_url)
    source = session.get(Source, source_id)
    if source is None:
        return redirect_with_flash(target, "信源不存在", param="err")
    try:
        StateMachineExecutor().execute(
            SourceRejectProposal(
                payload=SourceRejectPayload(source_id=source_id), rationale=REJECT_RATIONALE
            ),
            session=session,
        )
    except ProposalRejectedError as exc:
        return redirect_with_flash(target, "；".join(exc.reasons), param="err")
    return redirect_with_flash(target, f"已拒绝（留痕）：{source.name}")
