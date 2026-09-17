"""信源库页（doc-07 §2.1、§3，原型「信源库/信源画像」页）。

列表（主体 / 途径两栏）+ 待确认信源确认闭环 + 信源画像（信用档与调整历史、途径、
参与条目）。人工登记入口已下线（IIH-06.01 通路反转）——新信源一律经条目归因
识别进待确认队列（decision-05）。
"""

from difflib import SequenceMatcher
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

CONFIRM_RATIONALE = "人工确认（decision-05 准入把关）"
REJECT_RATIONALE = "人工拒绝（decision-05 准入把关）"

# IIH-06.01 ②相似名查重：纯提示不自动归并（用户裁决）。归一化=去空白+lower；
# difflib SequenceMatcher.ratio() 自带归一化相似度。阈值 0.7——「中国工业报」vs
# 「中国工业报社」≈0.94 命中，「中国装备」vs「中国装备制造」≈0.67 不命中。
SIMILARITY_THRESHOLD = 0.7


def _normalize_name(name: str) -> str:
    return "".join(name.lower().split())


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _normalize_name(a), _normalize_name(b)).ratio()


def _find_similar_confirmed(name: str, candidates: list[Source]) -> list[Source]:
    if not name:
        return []
    return [s for s in candidates if _similarity(name, s.name) >= SIMILARITY_THRESHOLD]


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


def _render(request: Request, session: Session, flash: str = "", err: str = ""):
    confirmed = _confirmed_sources(session)
    pending = _pending_sources(session)
    pending_similars = {s.id: _find_similar_confirmed(s.name, confirmed) for s in pending}
    return templates.TemplateResponse(
        request,
        "sources.html",
        {
            **base_context(session, "sources"),
            "sources": confirmed,
            "pending_sources": pending,
            "pending_similars": pending_similars,
            "feedback_counts": _feedback_counts(session),
            "source_types": list(SOURCE_TYPE_LABELS.items()),
            "source_type_labels": SOURCE_TYPE_LABELS,
            "flash": flash,
            "err": err,
        },
    )


@router.get("/sources")
def sources_page(
    request: Request, flash: str = "", err: str = "", session: Session = Depends(get_session)
):
    return _render(request, session, flash=flash, err=err)


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
    confirmed = _confirmed_sources(session)
    pending_similars: dict[int, list[Source]] = {}
    if not source.confirmed:
        pending_similars[source.id] = _find_similar_confirmed(source.name, confirmed)
    return templates.TemplateResponse(
        request,
        "source_detail.html",
        {
            **base_context(session, "sources"),
            "source": source,
            "adjustments": adjustments,
            "participating": participating,
            "pending_similars": pending_similars,
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
    outlet_name: str = Form(""),
    outlet_entry: str = Form(""),
    next_url: str = Form("", alias="next"),
    session: Session = Depends(get_session),
):
    """待确认信源确认入池（IIH-05.01）：可修正名/类型 + 初始档 + 途径 → 提案落账。

    途径（IIH-05.02 补救）：采集入口非空即建互联网途径（名默认「网站」），
    预填发现来源 URL；留空不建（兼容人工归因的待确认信源）。
    """
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
                    outlet_name=outlet_name.strip() or None,
                    outlet_entry=outlet_entry.strip() or None,
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
