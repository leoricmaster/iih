"""核实智能体 Verifier 单测（doc-06 §5）：确定性评级，不调 LLM。

本里程碑最简版：穿透转引链统计 N → 取 source.credit 作 R → 按公式出 credibility → 组装 rating。
R=None → UNDETERMINED；R 有值 → VERIFIED。不调 LLM、不计量。
"""

from datetime import UTC, datetime

from sqlalchemy import select

from iih.agents.verifier import Verifier
from iih.ledger.formula import CONTENT_CREDIBILITY_FORMULA_VERSION
from iih.ledger.models import (
    IntelligenceItem,
    ItemMode,
    ItemStatus,
    LlmCall,
    Medium,
    Modality,
    ProvenanceChainNode,
    Source,
    SourceType,
    VerificationOutcome,
    VerificationRecord,
)
from iih.ledger.proposal import VerificationProposal
from iih.ledger.state_machine import StateMachineExecutor


def _seed_candidate(
    db_session,
    *,
    credit: str | None = "B",
    extra_sources: int = 0,
    source_name: str = "W 公司",
) -> IntelligenceItem:
    """预置一条 Candidate 态条目 + 转引链节点（默认单节点；extra_sources>0 追加不同信源节点）。"""
    medium = db_session.scalars(select(Medium).where(Medium.code == "internet")).one()
    modality = db_session.scalars(select(Modality).where(Modality.code == "webpage")).one()
    source = Source(name=source_name, type=SourceType.COMPANY, confirmed=True, credit=credit)
    item = IntelligenceItem(
        statement="W 公司公告：与 Z 集团签署合资协议",
        status=ItemStatus.CANDIDATE,
        mode=ItemMode.AUTOMATED,
        medium=medium,
        modality=modality,
        collected_at=datetime(2026, 9, 14, 10, 0, tzinfo=UTC),
        original_snapshot="正文",
        source=source,
    )
    db_session.add_all([source, item])
    db_session.flush()

    node = ProvenanceChainNode(
        item=item,
        source=source,
        modality=modality,
        medium=medium,
        collected_at=datetime(2026, 9, 14, 10, 0, tzinfo=UTC),
    )
    db_session.add(node)

    for i in range(extra_sources):
        extra_source = Source(
            name=f"行业媒体 {chr(ord('A') + i)}",
            type=SourceType.MEDIA,
            confirmed=True,
            credit="C",
        )
        db_session.add(extra_source)
        db_session.flush()
        extra_node = ProvenanceChainNode(
            item=item,
            source=extra_source,
            modality=modality,
            medium=medium,
            collected_at=datetime(2026, 9, 14, 11, 0, tzinfo=UTC),
        )
        db_session.add(extra_node)

    db_session.flush()
    return item


def test_verify_with_credit_b_produces_verified_b2(db_session) -> None:
    """支撑 IIH-01.03 AC#1：N=1 + R=B → 公式出 credibility=2，组装评级 B2。"""
    item = _seed_candidate(db_session, credit="B")
    verifier = Verifier(session=db_session)

    proposal = verifier.verify(item)

    assert isinstance(proposal, VerificationProposal)
    assert proposal.payload.item_id == item.id
    assert proposal.payload.outcome is VerificationOutcome.VERIFIED
    assert proposal.payload.independent_source_count == 1
    assert proposal.payload.source_reliability == "B"
    assert proposal.payload.content_credibility == 2
    assert proposal.payload.rating == "B2"
    assert proposal.formula_version == CONTENT_CREDIBILITY_FORMULA_VERSION
    assert "N=1" in proposal.rationale
    assert "R=B" in proposal.rationale


def test_verify_formula_branches_cover_all_reliability_grades(db_session) -> None:
    """公式覆盖：R=A/B→2、R=C→3、R=D/E→4、R=F→6（N=1）。"""
    cases = [("A", 2), ("B", 2), ("C", 3), ("D", 4), ("E", 4), ("F", 6)]
    for i, (credit, expected_credibility) in enumerate(cases):
        item = _seed_candidate(db_session, credit=credit, source_name=f"W 公司 {i}")
        verifier = Verifier(session=db_session)

        proposal = verifier.verify(item)

        assert proposal.payload.outcome is VerificationOutcome.VERIFIED
        assert proposal.payload.source_reliability == credit
        assert proposal.payload.content_credibility == expected_credibility
        assert proposal.payload.rating == f"{credit}{expected_credibility}"


def test_verify_multi_source_returns_credibility_1(db_session) -> None:
    """N≥2 → credibility=1（多信源场景：预置 2 节点不同 source_id）。"""
    item = _seed_candidate(db_session, credit="B", extra_sources=1)
    verifier = Verifier(session=db_session)

    proposal = verifier.verify(item)

    assert proposal.payload.independent_source_count == 2
    assert proposal.payload.content_credibility == 1
    assert proposal.payload.rating == "B1"


def test_verify_no_credit_produces_undetermined(db_session) -> None:
    """支撑 IIH-01.03 AC#2：R=None（信源画像未设信用档）→ UNDETERMINED。"""
    item = _seed_candidate(db_session, credit=None)
    verifier = Verifier(session=db_session)

    proposal = verifier.verify(item)

    assert proposal.payload.outcome is VerificationOutcome.UNDETERMINED
    assert proposal.payload.independent_source_count == 1
    assert proposal.payload.source_reliability is None
    assert proposal.payload.content_credibility is None
    assert proposal.payload.rating is None
    assert proposal.formula_version is None
    assert "未设信用档" in proposal.rationale


def test_verify_does_not_call_llm_or_meter(db_session) -> None:
    """核实智能体最简版纯确定性，不调 LLM、不计量（无 LlmCall 写入）。"""
    item = _seed_candidate(db_session, credit="B")
    verifier = Verifier(session=db_session)

    verifier.verify(item)

    assert len(db_session.scalars(select(LlmCall)).all()) == 0


def test_verify_pass_then_execute_lands_verified_and_record(db_session) -> None:
    """端到端：VERIFIED 提案 → 状态机 → Candidate → Verified + VerificationRecord。"""
    item = _seed_candidate(db_session, credit="B")
    verifier = Verifier(session=db_session)

    proposal = verifier.verify(item)
    StateMachineExecutor().execute(proposal, session=db_session)

    refreshed = db_session.get(IntelligenceItem, item.id)
    assert refreshed is not None
    assert refreshed.status is ItemStatus.VERIFIED
    assert refreshed.rating == "B2"

    records = db_session.scalars(
        select(VerificationRecord).where(VerificationRecord.item_id == item.id)
    ).all()
    assert len(records) == 1
    assert records[0].outcome is VerificationOutcome.VERIFIED
    assert records[0].rating == "B2"
    assert records[0].formula_version == CONTENT_CREDIBILITY_FORMULA_VERSION


def test_verify_no_credit_then_execute_lands_undetermined(db_session) -> None:
    """端到端：UNDETERMINED 提案 → 状态机 → Candidate → Undetermined + Record。"""
    item = _seed_candidate(db_session, credit=None)
    verifier = Verifier(session=db_session)

    proposal = verifier.verify(item)
    StateMachineExecutor().execute(proposal, session=db_session)

    refreshed = db_session.get(IntelligenceItem, item.id)
    assert refreshed is not None
    assert refreshed.status is ItemStatus.UNDETERMINED
    assert refreshed.rating is None

    records = db_session.scalars(
        select(VerificationRecord).where(VerificationRecord.item_id == item.id)
    ).all()
    assert len(records) == 1
    assert records[0].outcome is VerificationOutcome.UNDETERMINED
    assert records[0].rating is None
    assert records[0].formula_version is None
