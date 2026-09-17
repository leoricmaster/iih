"""信源库页（doc-07 §2.1、§3，原型「信源库/信源画像」页）。

列表（主体 / 采集入口两栏）+ 待确认信源确认闭环 + 信源画像（信用档与调整历史、
采集入口、参与条目）。人工登记入口已下线（IIH-06.01 通路反转）——新信源一律经
条目归因识别进待确认队列（decision-05）。
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
    Entry,
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
    """已确认信源列表，采集入口经关系加载（doc-03 §六：主体/采集入口两栏）。"""
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
    edit: str = "",
    session: Session = Depends(get_session),
):
    """信源画像：信用（档 + 调整历史）+ 采集入口 + 参与条目（转引链出现即计）。"""
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
            "edit_mode": edit == "1",
        },
    )


@router.post("/sources/{source_id}/edit")
def source_edit(
    source_id: int,
    request: Request,
    name: str = Form(""),
    aliases: list[str] = Form(default=[]),
    credit: str = Form(""),
    entry_id: list[int] = Form(default=[]),
    entry_value: list[str] = Form(default=[]),
    entry_delete_ids: list[int] = Form(default=[]),
    session: Session = Depends(get_session),
):
    """画像页统一编辑态：单端点批量保存主体名/别名/信用档/采集入口。"""
    source = session.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="信源不存在")
    if not source.confirmed:
        return redirect_with_flash(
            f"/sources/{source_id}", "待确认信源不入库、不建画像、不记账", param="err"
        )

    err = _apply_source_edit(
        session,
        source,
        name=name,
        aliases=aliases,
        credit=credit,
        entry_id=entry_id,
        entry_value=entry_value,
        entry_delete_ids=entry_delete_ids,
    )
    if err is not None:
        return RedirectResponse(
            f"/sources/{source_id}?edit=1&err={quote_plus(err)}", status_code=303
        )
    return redirect_with_flash(f"/sources/{source_id}", "已保存")


def _apply_source_edit(
    session: Session,
    source: Source,
    *,
    name: str,
    aliases: list[str],
    credit: str,
    entry_id: list[int],
    entry_value: list[str],
    entry_delete_ids: list[int],
) -> str | None:
    """单事务应用编辑态变更。返回 err 字符串；None 表示成功。"""
    new_name = name.strip()
    if not new_name:
        return "名称不能为空"
    existing_aliases: dict[str, SourceAlias | None] = {a.name: a for a in source.aliases}
    if new_name != source.name:
        dup = session.scalars(
            select(Source).where(Source.name == new_name, Source.id != source.id)
        ).first()
        if dup is not None:
            return f"已存在同名信源：{new_name}"
        alias_hit = session.scalars(select(SourceAlias).where(SourceAlias.name == new_name)).first()
        if alias_hit is not None and alias_hit.source_id != source.id:
            return f"已存在同名别名（归属 {alias_hit.source.name}）：{new_name}"
        session.add(SourceAlias(source=source, name=source.name))
        existing_aliases[source.name] = None
        source.name = new_name

    new_aliases = [a.strip() for a in aliases if a.strip()]
    new_alias_set = {a for a in new_aliases if a != source.name}
    for name_str, alias_obj in existing_aliases.items():
        if alias_obj is None:
            continue
        if name_str not in new_alias_set:
            session.delete(alias_obj)
    for name_str in new_alias_set:
        if name_str in existing_aliases:
            continue
        dup = session.scalars(select(Source).where(Source.name == name_str)).first()
        if dup is not None and dup.id != source.id:
            return f"已存在同名信源：{name_str}"
        alias_hit = session.scalars(select(SourceAlias).where(SourceAlias.name == name_str)).first()
        if alias_hit is not None and alias_hit.source_id != source.id:
            return f"已存在同名别名（归属 {alias_hit.source.name}）：{name_str}"
        session.add(SourceAlias(source=source, name=name_str))

    grade = credit.strip()
    if grade and grade not in "ABCDEF":
        return f"信用档需为 A–F 或不设：{grade}"
    source.credit = grade or None

    for eid in entry_delete_ids:
        if eid:
            existing = session.get(Entry, eid)
            if existing is not None and existing.source_id == source.id:
                session.delete(existing)

    seen_entries: set[str] = set()
    for i, eid in enumerate(entry_id):
        value = entry_value[i].strip() if i < len(entry_value) else ""
        if not value:
            continue
        if value in seen_entries:
            return f"采集入口重复：{value}"
        seen_entries.add(value)
        if eid:
            existing = session.get(Entry, eid)
            if existing is None or existing.source_id != source.id:
                return f"采集入口引用不存在：{value}"
            dup_entry = session.scalars(
                select(Entry).where(
                    Entry.source_id == source.id,
                    Entry.entry == value,
                    Entry.id != eid,
                )
            ).first()
            if dup_entry is not None:
                return f"采集入口重复：{value}"
            existing.entry = value
        else:
            session.add(Entry(source=source, entry=value))

    session.commit()
    return None


@router.post("/sources/{source_id}/confirm")
def source_confirm(
    source_id: int,
    request: Request,
    initial_credit: str = Form(""),
    name: str = Form(""),
    source_type: str = Form(""),
    entry: str = Form(""),
    next_url: str = Form("", alias="next"),
    session: Session = Depends(get_session),
):
    """待确认信源确认入池（IIH-05.01）：可修正名/类型 + 初始档 + 采集入口 → 提案落账。

    采集入口（IIH-05.02 补救、IIH-06.03 途径退役）：非空即建（预填发现来源 URL），
    留空不建（兼容人工归因的待确认信源）。
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
                    entry=entry.strip() or None,
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
