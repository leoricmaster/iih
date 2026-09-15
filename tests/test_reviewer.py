"""审查智能体 Reviewer 单测（doc-06 §4 + IIH-03.01 时效否决）。"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from conftest import make_fake_llm_review
from iih.agents.reviewer import Reviewer
from iih.ledger.models import (
    IntelligenceItem,
    IntelligenceRequirement,
    IntelligenceRequirementStatus,
    ItemMode,
    ItemStatus,
    LlmCall,
    Medium,
    Modality,
    RejectionReasonEnum,
    ReviewDecision,
    ReviewDecisionEnum,
    Source,
    SourceType,
)
from iih.ledger.proposal import ReviewProposal
from iih.ledger.state_machine import StateMachineExecutor


def _seed_lead_and_active_ir(
    db_session, statement: str = "W 公司公告：与 Z 集团签署合资协议"
) -> tuple[IntelligenceItem, IntelligenceRequirement]:
    """预置 Lead 态条目 + 激活情报需求，返回 (item, ir)。"""
    medium = db_session.scalars(select(Medium).where(Medium.code == "internet")).one()
    modality = db_session.scalars(select(Modality).where(Modality.code == "webpage")).one()
    source = Source(name="W 公司", type=SourceType.COMPANY, confirmed=True)
    ir = IntelligenceRequirement(
        name="跟踪 W 公司",
        content_spec="主题：矿卡、订单、战略",
        status=IntelligenceRequirementStatus.ACTIVE,
    )
    item = IntelligenceItem(
        statement=statement,
        status=ItemStatus.LEAD,
        mode=ItemMode.AUTOMATED,
        medium=medium,
        modality=modality,
        collected_at=datetime(2026, 9, 14, 10, 0, tzinfo=UTC),
        original_snapshot="正文",
        source=source,
    )
    db_session.add_all([ir, item])
    db_session.flush()
    return item, ir


def test_review_pass_produces_proposal_with_matched_requirement(
    db_session, w_review_pass_factory
) -> None:
    """支撑 IIH-01.02 AC#1：Reviewer 调 LLM 判定通过，产出 PASS 提案 + matched_requirement_id。"""
    item, ir = _seed_lead_and_active_ir(db_session)
    judgment = w_review_pass_factory(matched_requirement_id=ir.id)
    reviewer = Reviewer(
        llm=make_fake_llm_review(judgment), session=db_session, model="deepseek-chat"
    )

    proposal = reviewer.review(item)

    assert isinstance(proposal, ReviewProposal)
    assert proposal.payload.item_id == item.id
    assert proposal.payload.decision is ReviewDecisionEnum.PASS
    assert proposal.payload.reason_type is None
    assert proposal.payload.matched_requirement_id == ir.id
    assert "命中激活需求" in proposal.rationale

    # LLM 调用计量入账
    calls = db_session.scalars(select(LlmCall)).all()
    assert len(calls) == 1
    assert calls[0].agent == "reviewer"
    assert calls[0].target == "item_review"


def test_review_reject_irrelevant_produces_proposal_with_reason(
    db_session, w_review_reject_irrelevant
) -> None:
    """支撑 IIH-01.02 AC#2：Reviewer 调 LLM 判定否决，产出 REJECT 提案 + reason_type。"""
    item, _ir = _seed_lead_and_active_ir(db_session)
    reviewer = Reviewer(
        llm=make_fake_llm_review(w_review_reject_irrelevant),
        session=db_session,
        model="deepseek-chat",
    )

    proposal = reviewer.review(item)

    assert proposal.payload.decision is ReviewDecisionEnum.REJECT
    assert proposal.payload.reason_type is RejectionReasonEnum.IRRELEVANT
    assert proposal.payload.matched_requirement_id is None

    # 端到端：落账后状态迁移
    StateMachineExecutor().execute(proposal, session=db_session)
    assert db_session.get(IntelligenceItem, item.id).status is ItemStatus.NOISE


def test_review_reject_invalid_produces_proposal_with_reason(
    db_session, w_review_reject_invalid
) -> None:
    """有效性初筛失败→REJECT/INVALID。"""
    item, _ir = _seed_lead_and_active_ir(db_session)
    reviewer = Reviewer(
        llm=make_fake_llm_review(w_review_reject_invalid), session=db_session, model="deepseek-chat"
    )

    proposal = reviewer.review(item)

    assert proposal.payload.decision is ReviewDecisionEnum.REJECT
    assert proposal.payload.reason_type is RejectionReasonEnum.INVALID


def test_review_no_active_ir_rejects_without_llm(db_session) -> None:
    """无激活情报需求时直接 REJECT/IRRELEVANT，不调 LLM、不计量。"""
    # 只预置 Lead 条目，不预置激活 IR
    medium = db_session.scalars(select(Medium).where(Medium.code == "internet")).one()
    modality = db_session.scalars(select(Modality).where(Modality.code == "webpage")).one()
    source = Source(name="W 公司", type=SourceType.COMPANY, confirmed=True)
    item = IntelligenceItem(
        statement="某陈述",
        status=ItemStatus.LEAD,
        mode=ItemMode.AUTOMATED,
        medium=medium,
        modality=modality,
        collected_at=datetime(2026, 9, 14, 10, 0, tzinfo=UTC),
        original_snapshot="x",
        source=source,
    )
    db_session.add(item)
    db_session.flush()

    # fake LLM 若被调用会断言失败（response_model 不匹配）；此处不应被调用
    class FailingCompletions:
        def create_with_completion(self, *, response_model, messages, **kwargs):
            raise AssertionError("无激活 IR 时不应调 LLM")

    fake_llm = type(
        "FakeLLM",
        (),
        {"chat": type("C", (), {"completions": FailingCompletions()})()},
    )
    reviewer = Reviewer(llm=fake_llm, session=db_session, model="deepseek-chat")

    proposal = reviewer.review(item)

    assert proposal.payload.decision is ReviewDecisionEnum.REJECT
    assert proposal.payload.reason_type is RejectionReasonEnum.IRRELEVANT
    assert proposal.payload.matched_requirement_id is None
    assert "无激活情报需求" in proposal.rationale
    # 不计量
    assert len(db_session.scalars(select(LlmCall)).all()) == 0


def test_review_pass_then_execute_lands_candidate_and_decision(
    db_session, w_review_pass_factory
) -> None:
    """端到端：Reviewer 产出 PASS 提案 → 状态机执行 → Lead → Candidate + ReviewDecision。"""
    item, ir = _seed_lead_and_active_ir(db_session)
    judgment = w_review_pass_factory(matched_requirement_id=ir.id)
    reviewer = Reviewer(
        llm=make_fake_llm_review(judgment), session=db_session, model="deepseek-chat"
    )

    proposal = reviewer.review(item)
    StateMachineExecutor().execute(proposal, session=db_session)

    refreshed = db_session.get(IntelligenceItem, item.id)
    assert refreshed is not None
    assert refreshed.status is ItemStatus.CANDIDATE

    decisions = db_session.scalars(
        select(ReviewDecision).where(ReviewDecision.item_id == item.id)
    ).all()
    assert len(decisions) == 1
    assert decisions[0].decision is ReviewDecisionEnum.PASS
    assert decisions[0].matched_requirement_id == ir.id


# ---- IIH-03.01 事件时效否决 ----


def _seed_lead_with_event_time(
    db_session, *, event_time: datetime | None, statement: str = "W 公司公告"
) -> IntelligenceItem:
    medium = db_session.scalars(select(Medium).where(Medium.code == "internet")).one()
    modality = db_session.scalars(select(Modality).where(Modality.code == "webpage")).one()
    source = Source(name="W 公司", type=SourceType.COMPANY, confirmed=True)
    item = IntelligenceItem(
        statement=statement,
        status=ItemStatus.LEAD,
        mode=ItemMode.AUTOMATED,
        medium=medium,
        modality=modality,
        collected_at=datetime(2026, 9, 14, 10, 0, tzinfo=UTC),
        original_snapshot="正文",
        source=source,
        event_time=event_time,
    )
    db_session.add(item)
    db_session.flush()
    return item


def test_freshness_rejects_expired_event(db_session) -> None:
    """IR 配 7d 时效，item.event_time 早于 7 天前 → 全部 IR 过期 → REJECT IRRELEVANT。"""
    item = _seed_lead_with_event_time(db_session, event_time=datetime.now(UTC) - timedelta(days=30))
    ir = IntelligenceRequirement(
        name="跟踪 W 公司",
        content_spec="主题",
        status=IntelligenceRequirementStatus.ACTIVE,
        event_freshness="7d",
    )
    db_session.add(ir)
    db_session.flush()

    # 若 LLM 被调用会断言失败
    class FailingCompletions:
        def create_with_completion(self, *, response_model, messages, **kwargs):
            raise AssertionError("全部 IR 过期时不应调 LLM")

    fake_llm = type("FakeLLM", (), {"chat": type("C", (), {"completions": FailingCompletions()})()})
    reviewer = Reviewer(llm=fake_llm, session=db_session, model="deepseek-chat")

    proposal = reviewer.review(item)

    assert proposal.payload.decision is ReviewDecisionEnum.REJECT
    assert proposal.payload.reason_type is RejectionReasonEnum.IRRELEVANT
    assert "时效过期" in proposal.rationale


def test_freshness_keeps_recent_event(db_session, w_review_pass_factory) -> None:
    """IR 配 7d 时效，item.event_time 在 7 天内 → IR 保留，调 LLM 判断。"""
    item = _seed_lead_with_event_time(db_session, event_time=datetime.now(UTC) - timedelta(days=2))
    ir = IntelligenceRequirement(
        name="跟踪 W 公司",
        content_spec="主题",
        status=IntelligenceRequirementStatus.ACTIVE,
        event_freshness="7d",
    )
    db_session.add(ir)
    db_session.flush()

    judgment = w_review_pass_factory(matched_requirement_id=ir.id)
    reviewer = Reviewer(
        llm=make_fake_llm_review(judgment), session=db_session, model="deepseek-chat"
    )

    proposal = reviewer.review(item)

    assert proposal.payload.decision is ReviewDecisionEnum.PASS
    assert proposal.payload.matched_requirement_id == ir.id


def test_freshness_empty_keeps_all(db_session, w_review_pass_factory) -> None:
    """IR 时效为空 → 不限时效，无论 event_time 多早都保留。"""
    item = _seed_lead_with_event_time(
        db_session, event_time=datetime.now(UTC) - timedelta(days=365)
    )
    ir = IntelligenceRequirement(
        name="跟踪 W 公司",
        content_spec="主题",
        status=IntelligenceRequirementStatus.ACTIVE,
        event_freshness=None,
    )
    db_session.add(ir)
    db_session.flush()

    judgment = w_review_pass_factory(matched_requirement_id=ir.id)
    reviewer = Reviewer(
        llm=make_fake_llm_review(judgment), session=db_session, model="deepseek-chat"
    )

    proposal = reviewer.review(item)

    assert proposal.payload.decision is ReviewDecisionEnum.PASS


def test_freshness_item_no_event_time_keeps_all(db_session, w_review_pass_factory) -> None:
    """item.event_time 为空 → 不卡时效（无事件时间不否决）。"""
    item = _seed_lead_with_event_time(db_session, event_time=None)
    ir = IntelligenceRequirement(
        name="跟踪 W 公司",
        content_spec="主题",
        status=IntelligenceRequirementStatus.ACTIVE,
        event_freshness="7d",
    )
    db_session.add(ir)
    db_session.flush()

    judgment = w_review_pass_factory(matched_requirement_id=ir.id)
    reviewer = Reviewer(
        llm=make_fake_llm_review(judgment), session=db_session, model="deepseek-chat"
    )

    proposal = reviewer.review(item)

    assert proposal.payload.decision is ReviewDecisionEnum.PASS


def test_freshness_mixed_ir_filters_only_expired(db_session, w_review_pass_factory) -> None:
    """两个 IR：一个配 7d 时效（过期），一个不配（保留）→ 调 LLM 判断保留的 IR。"""
    item = _seed_lead_with_event_time(db_session, event_time=datetime.now(UTC) - timedelta(days=30))
    expired_ir = IntelligenceRequirement(
        name="7d 限制",
        content_spec="主题",
        status=IntelligenceRequirementStatus.ACTIVE,
        event_freshness="7d",
    )
    fresh_ir = IntelligenceRequirement(
        name="不限时效",
        content_spec="主题",
        status=IntelligenceRequirementStatus.ACTIVE,
    )
    db_session.add_all([expired_ir, fresh_ir])
    db_session.flush()

    judgment = w_review_pass_factory(matched_requirement_id=fresh_ir.id)
    reviewer = Reviewer(
        llm=make_fake_llm_review(judgment), session=db_session, model="deepseek-chat"
    )

    proposal = reviewer.review(item)

    assert proposal.payload.decision is ReviewDecisionEnum.PASS
    assert proposal.payload.matched_requirement_id == fresh_ir.id
