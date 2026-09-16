"""情报需求页（doc-07 §3，原型「情报需求」页）：列表 + 详情 + 声明与生命周期动作。

迁移经提案落账（doc-02 §4.1：确认激活 / 挂起 / 恢复 / 关闭）；
内容规格微调与采集配置编辑为消费方配置编辑（非智能体写入，直接更新字段）。
配置自检（试采集预览）：逐途径抓取→抽取→按本需求审查预判，不落账。
覆盖度量（已分发/已消费）待分发记录里程碑加厚，本页以命中计数近似。
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from iih.agents.collector import Collector
from iih.agents.director import CollectionTask
from iih.agents.reviewer import Reviewer
from iih.config import get_settings
from iih.ledger.duration import parse_duration_to_seconds
from iih.ledger.models import (
    IntelligenceItem,
    IntelligenceRequirement,
    IntelligenceRequirementStatus,
    Outlet,
    ReviewDecision,
    Source,
)
from iih.ledger.proposal import (
    IntelligenceRequirementActivatePayload,
    IntelligenceRequirementActivateProposal,
    IntelligenceRequirementClosePayload,
    IntelligenceRequirementCloseProposal,
    IntelligenceRequirementPausePayload,
    IntelligenceRequirementPauseProposal,
    IntelligenceRequirementRegisterPayload,
    IntelligenceRequirementRegisterProposal,
    IntelligenceRequirementResumePayload,
    IntelligenceRequirementResumeProposal,
    ItemProvenanceAppendProposal,
)
from iih.ledger.state_machine import ProposalRejectedError, StateMachineExecutor
from iih.tools.fetcher import FetcherError, fetch
from iih.web.context import (
    REJECTION_REASON_LABELS,
    STATUS_LABELS,
    base_context,
    register_template_filters,
)
from iih.web.deps import get_llm_client, get_session
from iih.web.flash import redirect_with_flash

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = register_template_filters(Jinja2Templates(directory=TEMPLATES_DIR))

router = APIRouter()

IR_STATUS_LABELS = {
    IntelligenceRequirementStatus.DRAFT: "草稿",
    IntelligenceRequirementStatus.ACTIVE: "激活",
    IntelligenceRequirementStatus.PAUSED: "暂停",
    IntelligenceRequirementStatus.CLOSED: "关闭",
}

GROUP_ORDER = [
    IntelligenceRequirementStatus.ACTIVE,
    IntelligenceRequirementStatus.DRAFT,
    IntelligenceRequirementStatus.PAUSED,
    IntelligenceRequirementStatus.CLOSED,
]

ACTION_PROPOSALS = {
    "activate": (IntelligenceRequirementActivatePayload, IntelligenceRequirementActivateProposal),
    "pause": (IntelligenceRequirementPausePayload, IntelligenceRequirementPauseProposal),
    "resume": (IntelligenceRequirementResumePayload, IntelligenceRequirementResumeProposal),
    "close": (IntelligenceRequirementClosePayload, IntelligenceRequirementCloseProposal),
}


def _hit_item_ids(session: Session, requirement_id: int) -> list[int]:
    """命中条目：审查通过记录里匹配本需求的条目。"""
    return list(
        session.scalars(
            select(ReviewDecision.item_id).where(
                ReviewDecision.matched_requirement_id == requirement_id
            )
        )
    )


def _collect_outlets(session: Session) -> list[Outlet]:
    """采集覆盖：已确认信源 × 互联网途径 × 入口非空（Director 同口径，doc-06 §2）。"""
    outlets = list(
        session.scalars(
            select(Outlet)
            .join(Source, Outlet.source_id == Source.id)
            .where(Source.confirmed.is_(True))
            .where(Outlet.medium.has())
        )
    )
    return [o for o in outlets if o.medium is not None and o.medium.code == "internet" and o.entry]


def _confirmed_sources(session: Session) -> list[Source]:
    """已确认信源列表（用于信源绑定 checkbox）。"""
    return list(
        session.scalars(select(Source).where(Source.confirmed.is_(True)).order_by(Source.name))
    )


def _format_valid_window(ir: IntelligenceRequirement) -> str:
    """生效窗口展示：起止任一可空。"""
    if ir.valid_from is None and ir.valid_until is None:
        return "常驻"
    parts: list[str] = []
    parts.append(ir.valid_from.isoformat() if ir.valid_from else "—")
    parts.append(ir.valid_until.isoformat() if ir.valid_until else "不限")
    return " ~ ".join(parts)


def _format_sources(ir: IntelligenceRequirement) -> str:
    """信源绑定展示：空=全部。"""
    if not ir.sources:
        return "全部"
    return "、".join(s.name for s in ir.sources)


def _parse_date(s: str | None) -> date | None:
    """日期文本解析；空或非法返回 None。"""
    if not s or not s.strip():
        return None
    try:
        return date.fromisoformat(s.strip())
    except ValueError:
        return None


def _parse_explore_ratio(s: str | None, errors: list[str]) -> float | None:
    """池外探索比例解析：空=None=0；非法值入 errors 返回 None。"""
    if not s or not s.strip():
        return None
    try:
        value = float(s.strip())
    except ValueError:
        errors.append(f"池外探索比例非法：{s}（须 0–1 数字）")
        return None
    if not 0 <= value <= 1:
        errors.append(f"池外探索比例非法：{value}（须 0–1）")
        return None
    return value


@router.get("/requirements")
def requirements_page(request: Request, session: Session = Depends(get_session)):
    requirements = list(
        session.scalars(
            select(IntelligenceRequirement).order_by(
                IntelligenceRequirement.created_at.desc(), IntelligenceRequirement.id.desc()
            )
        )
    )
    # 单表按状态序（激活在前），组内保持创建时间倒序（稳定排序）
    status_order = {status: i for i, status in enumerate(GROUP_ORDER)}
    requirements.sort(key=lambda r: status_order[r.status])
    hit_counts = {r.id: len(_hit_item_ids(session, r.id)) for r in requirements}
    return templates.TemplateResponse(
        request,
        "requirements.html",
        {
            **base_context(session, "reqs"),
            "requirements": requirements,
            "hit_counts": hit_counts,
            "status_labels": IR_STATUS_LABELS,
            "item_status_labels": STATUS_LABELS,
            "confirmed_sources": _confirmed_sources(session),
            "format_window": _format_valid_window,
            "format_sources": _format_sources,
        },
    )


@router.post("/requirements")
def requirement_create(
    request: Request,
    name: str = Form(""),
    content_spec: str = Form(""),
    collection_frequency: str = Form(""),
    event_freshness: str = Form(""),
    valid_from: str = Form(""),
    valid_until: str = Form(""),
    explore_ratio: str = Form(""),
    source_ids: list[int] = Form([]),
    session: Session = Depends(get_session),
):
    """新建情报需求：[*] → 草稿 Draft（doc-02 §4.1）+ 需求级采集配置（IIH-03.01/05.02）。"""
    errors: list[str] = []
    if not name.strip():
        errors.append("请填写需求名称")
    if not content_spec.strip():
        errors.append("请填写内容规格")
    frequency = collection_frequency.strip() or None
    freshness = event_freshness.strip() or None
    if frequency and parse_duration_to_seconds(frequency) is None:
        errors.append(f"采集频率格式非法：{frequency}（须 Nh/Nd/Nw/Nm）")
    if freshness and parse_duration_to_seconds(freshness) is None:
        errors.append(f"事件时效格式非法：{freshness}（须 Nh/Nd/Nw/Nm）")
    v_from = _parse_date(valid_from)
    v_until = _parse_date(valid_until)
    if v_from and v_until and v_until < v_from:
        errors.append("生效窗口结束日早于起始日")
    ratio = _parse_explore_ratio(explore_ratio, errors)
    bound_sources: list[Source] = []
    for sid in source_ids:
        src = session.get(Source, sid)
        if src is None or not src.confirmed:
            errors.append(f"信源不可绑定：{sid}")
        else:
            bound_sources.append(src)

    if errors:
        requirements = list(session.scalars(select(IntelligenceRequirement)))
        status_order = {status: i for i, status in enumerate(GROUP_ORDER)}
        requirements.sort(key=lambda r: status_order[r.status])
        return templates.TemplateResponse(
            request,
            "requirements.html",
            {
                **base_context(session, "reqs"),
                "requirements": requirements,
                "hit_counts": {r.id: len(_hit_item_ids(session, r.id)) for r in requirements},
                "status_labels": IR_STATUS_LABELS,
                "item_status_labels": STATUS_LABELS,
                "confirmed_sources": _confirmed_sources(session),
                "format_window": _format_valid_window,
                "format_sources": _format_sources,
                "errors": errors,
                "form_name": name,
                "form_spec": content_spec,
                "form_frequency": collection_frequency,
                "form_freshness": event_freshness,
                "form_valid_from": valid_from,
                "form_valid_until": valid_until,
                "form_explore_ratio": explore_ratio,
                "form_source_ids": source_ids,
            },
        )

    proposal = IntelligenceRequirementRegisterProposal(
        payload=IntelligenceRequirementRegisterPayload(
            name=name.strip(),
            content_spec=content_spec.strip(),
            collection_frequency=frequency,
            event_freshness=freshness,
            valid_from=v_from,
            valid_until=v_until,
            source_ids=[s.id for s in bound_sources],
            explore_ratio=ratio,
        ),
        rationale="Web 登记（消费方声明）",
    )
    try:
        result = StateMachineExecutor().execute(proposal, session=session)
    except ProposalRejectedError:
        return RedirectResponse("/requirements", status_code=303)
    return RedirectResponse(f"/requirements/{result.requirement_id}", status_code=303)


def _hit_items(session: Session, requirement_id: int) -> list[IntelligenceItem]:
    ids = _hit_item_ids(session, requirement_id)
    if not ids:
        return []
    return list(
        session.scalars(
            select(IntelligenceItem)
            .where(IntelligenceItem.id.in_(ids))
            .order_by(IntelligenceItem.created_at.desc(), IntelligenceItem.id.desc())
        )
    )


def _render_detail(
    request: Request,
    session: Session,
    requirement_id: int,
    *,
    errors: list[str] | None = None,
    flash: str = "",
    probe_results: list["ProbeResult"] | None = None,
):
    ir = session.get(IntelligenceRequirement, requirement_id)
    if ir is None:
        raise HTTPException(status_code=404, detail="情报需求不存在")
    return templates.TemplateResponse(
        request,
        "requirement_detail.html",
        {
            **base_context(session, "reqs"),
            "ir": ir,
            "status_labels": IR_STATUS_LABELS,
            "item_status_labels": STATUS_LABELS,
            "hit_items": _hit_items(session, requirement_id),
            "collect_outlets": _collect_outlets(session),
            "confirmed_sources": _confirmed_sources(session),
            "format_window": _format_valid_window,
            "format_sources": _format_sources,
            "errors": errors or [],
            "flash": flash,
            "probe_results": probe_results,
        },
    )


@router.get("/requirements/{requirement_id}")
def requirement_detail(
    requirement_id: int,
    request: Request,
    flash: str = "",
    session: Session = Depends(get_session),
):
    return _render_detail(request, session, requirement_id, flash=flash)


@router.post("/requirements/{requirement_id}/action")
def requirement_action(
    requirement_id: int,
    request: Request,
    action: str = Form(""),
    session: Session = Depends(get_session),
):
    """生命周期动作：确认激活 / 暂停 / 恢复 / 关闭（doc-02 §4.1，经提案落账）。"""
    payload_cls, proposal_cls = ACTION_PROPOSALS.get(action, (None, None))
    if payload_cls is None or proposal_cls is None:
        return _render_detail(request, session, requirement_id, errors=[f"未知动作：{action}"])

    proposal = proposal_cls(
        payload=payload_cls(requirement_id=requirement_id),
        rationale=f"Web {action}（消费方操作）",
    )
    try:
        StateMachineExecutor().execute(proposal, session=session)
    except ProposalRejectedError as exc:
        return _render_detail(request, session, requirement_id, errors=exc.reasons)
    return RedirectResponse(f"/requirements/{requirement_id}", status_code=303)


@router.post("/requirements/{requirement_id}/spec")
def requirement_spec_update(
    requirement_id: int,
    request: Request,
    content_spec: str = Form(""),
    session: Session = Depends(get_session),
):
    """内容规格微调（doc-07 §2.2 定期微调）：消费方配置编辑，生效于下轮采集。"""
    ir = session.get(IntelligenceRequirement, requirement_id)
    if ir is None:
        raise HTTPException(status_code=404, detail="情报需求不存在")
    if not content_spec.strip():
        return _render_detail(request, session, requirement_id, errors=["内容规格不能为空"])
    ir.content_spec = content_spec.strip()
    session.commit()
    return redirect_with_flash(f"/requirements/{requirement_id}", "内容规格已保存")


@router.post("/requirements/{requirement_id}/config")
def requirement_config_update(
    requirement_id: int,
    request: Request,
    collection_frequency: str = Form(""),
    event_freshness: str = Form(""),
    valid_from: str = Form(""),
    valid_until: str = Form(""),
    explore_ratio: str = Form(""),
    source_ids: list[int] = Form([]),
    session: Session = Depends(get_session),
):
    """采集配置编辑（IIH-03.01/05.02）：频率/时效/窗口/信源绑定/探索比例，直接更新字段。

    与 spec_update 同模式：消费方配置编辑非智能体写入，激活态可改。
    """
    ir = session.get(IntelligenceRequirement, requirement_id)
    if ir is None:
        raise HTTPException(status_code=404, detail="情报需求不存在")
    if ir.status is not IntelligenceRequirementStatus.ACTIVE:
        return _render_detail(request, session, requirement_id, errors=["仅激活态可编辑采集配置"])

    errors: list[str] = []
    frequency = collection_frequency.strip() or None
    freshness = event_freshness.strip() or None
    if frequency and parse_duration_to_seconds(frequency) is None:
        errors.append(f"采集频率格式非法：{frequency}（须 Nh/Nd/Nw/Nm）")
    if freshness and parse_duration_to_seconds(freshness) is None:
        errors.append(f"事件时效格式非法：{freshness}（须 Nh/Nd/Nw/Nm）")
    v_from = _parse_date(valid_from)
    v_until = _parse_date(valid_until)
    if v_from and v_until and v_until < v_from:
        errors.append("生效窗口结束日早于起始日")
    ratio = _parse_explore_ratio(explore_ratio, errors)
    bound_sources: list[Source] = []
    for sid in source_ids:
        src = session.get(Source, sid)
        if src is None or not src.confirmed:
            errors.append(f"信源不可绑定：{sid}")
        else:
            bound_sources.append(src)

    if errors:
        return _render_detail(request, session, requirement_id, errors=errors)

    ir.collection_frequency = frequency
    ir.event_freshness = freshness
    ir.valid_from = v_from
    ir.valid_until = v_until
    ir.explore_ratio = ratio
    ir.sources = bound_sources
    session.commit()
    return redirect_with_flash(f"/requirements/{requirement_id}", "采集配置已保存")


# ---- 配置自检（试采集预览 · 不落账，IIH-01.13 偏差 #7） ----


@dataclass
class ProbeResult:
    """单途径试采集预览结果（仅回显，不产生提案、不落账、不存快照对象）。"""

    source_name: str
    outlet_name: str
    url: str
    fetch_error: str | None = None
    article_url: str | None = None  # 选链结果（两跳：文章页地址；单跳：入口地址）
    statement: str | None = None
    extraction_note: str | None = None  # 无新内容 / 命中既有条目
    extraction_rationale: str | None = None
    decision: str | None = None  # 审查预判：pass / reject
    reason_type: str | None = None
    judgment_rationale: str | None = None
    judge_error: str | None = None


def _internet_outlets(session: Session) -> list[Outlet]:
    """试采集任务面：与 Director 同口径（已确认信源 × 互联网途径 × 入口非空）。"""
    outlets = list(
        session.scalars(
            select(Outlet)
            .join(Source, Outlet.source_id == Source.id)
            .where(Source.confirmed.is_(True))
        )
    )
    return [o for o in outlets if o.medium is not None and o.medium.code == "internet" and o.entry]


@router.post("/requirements/{requirement_id}/probe")
def requirement_probe(
    requirement_id: int,
    request: Request,
    session: Session = Depends(get_session),
    llm=Depends(get_llm_client),
):
    """配置自检：按本需求逐途径试采集，预览抽取与审查预判——不落账。

    供「激活后配置是否合理、能否抓到情报」的即时反馈（不等下轮采集）；
    已采集内容命中既有条目时提示将走转引链追加而非新建。LLM 调用照常计量。
    """
    ir = session.get(IntelligenceRequirement, requirement_id)
    if ir is None:
        raise HTTPException(status_code=404, detail="情报需求不存在")
    if ir.status is not IntelligenceRequirementStatus.ACTIVE:
        return _render_detail(
            request,
            session,
            requirement_id,
            errors=["仅激活态可试采集"],
        )

    outlets = _internet_outlets(session)
    if not outlets:
        return _render_detail(
            request,
            session,
            requirement_id,
            probe_results=[],
        )

    settings = get_settings()
    results: list[ProbeResult] = []
    for outlet in outlets:
        url = outlet.entry or ""  # _internet_outlets 已过滤空入口
        result = ProbeResult(source_name=outlet.source.name, outlet_name=outlet.name, url=url)
        task = CollectionTask(
            requirement_id=ir.id,
            requirement_name=ir.name,
            outlet_id=outlet.id,
            source_id=outlet.source_id,
            source_name=outlet.source.name,
            source_type=outlet.source.type,
            outlet_name=outlet.name,
            url=url,
            explore_ratio=0.0,  # 试采集预览不触发池外探索（避免 Tavily 副作用与费用）
            content_spec=ir.content_spec,
        )
        try:
            html = fetch(url)
            proposal = Collector(llm=llm, session=session, model=settings.llm_model).collect_outlet(
                task=task, html=html, fetch_article=fetch
            )
        except FetcherError as exc:
            result.fetch_error = str(exc)
            results.append(result)
            continue
        except Exception as exc:  # LLM 调用失败等
            result.extraction_note = f"采集失败：{exc}"
            results.append(result)
            continue

        if proposal is None:
            result.extraction_note = "无新内容（已采集或页面无情报价值）"
        elif isinstance(proposal, ItemProvenanceAppendProposal):
            result.article_url = proposal.payload.original_url
            result.extraction_note = (
                f"已采集内容命中既有条目 #{proposal.payload.item_id}"
                "——正式采集将追加转引链节点，不新建条目"
            )
        else:
            result.article_url = proposal.payload.original_url
            result.statement = proposal.payload.statement
            result.extraction_rationale = proposal.rationale
            try:
                reviewer = Reviewer(llm=llm, session=session, model=settings.llm_model)
                judgment = reviewer.judge_statement(
                    statement=proposal.payload.statement, requirements=[ir]
                )
            except Exception as exc:
                result.judge_error = str(exc)
                results.append(result)
                continue
            result.decision = judgment.decision.value
            result.reason_type = (
                REJECTION_REASON_LABELS.get(judgment.reason_type) if judgment.reason_type else None
            )
            result.judgment_rationale = judgment.rationale
        results.append(result)

    return _render_detail(request, session, requirement_id, probe_results=results)
