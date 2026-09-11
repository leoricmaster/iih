"""状态机执行器单测：通过落账 / 溯源缺失驳回 / 前置违反驳回（plan 阶段 3）。"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from iih.ledger.models import IntelligenceItem, ItemMode, ItemStatus, Outlet, Source
from iih.ledger.proposal import (
    IntelligenceItemNewPayload,
    IntelligenceItemNewProposal,
    Proposal,
    ProvenanceData,
)
from iih.ledger.state_machine import ExecutionResult, ProposalRejectedError, StateMachineExecutor

STATEMENT = "W 公司渠道大会：下一代电驱矿卡计划 2027Q2 量产"


def make_proposal(**overrides) -> IntelligenceItemNewProposal:
    """构造一份溯源五要素齐备的「情报条目新建」提案；kwargs 覆盖用于制造缺陷。"""
    provenance_fields = {
        "modality_code": "text",
        "medium_code": "meeting_discussion",
        "collected_at": datetime(2026, 9, 11, 10, 0, tzinfo=UTC),
        "original_snapshot": STATEMENT,
        "source_name": "W 公司",
        "source_type": "company",
        "outlet_name": "渠道大会现场",
    } | overrides.pop("provenance", {})
    payload_fields = {"statement": STATEMENT, "mode": ItemMode.MANUAL} | overrides.pop(
        "payload", {}
    )
    top_fields = {"rationale": "人工提交，归因自陈述"} | overrides
    return IntelligenceItemNewProposal(
        payload=IntelligenceItemNewPayload(**payload_fields),
        provenance=ProvenanceData(**provenance_fields),
        **top_fields,
    )


def test_commit_lands_lead_with_full_provenance(db_session) -> None:
    """支撑 IIH-01.01 AC#1：落账 Lead 与溯源五要素的记账层机制。"""
    result = StateMachineExecutor().execute(make_proposal(), session=db_session)

    assert isinstance(result, ExecutionResult)
    item = db_session.get(IntelligenceItem, result.item_id)
    assert item is not None
    assert item.status is ItemStatus.LEAD
    assert item.mode is ItemMode.MANUAL
    assert item.statement == STATEMENT
    # 溯源五要素：载体 + 媒介 + 采集时间 + 原文快照 + 信源/途径归因
    assert item.modality.code == "text"
    assert item.medium.code == "meeting_discussion"
    assert item.collected_at == datetime(2026, 9, 11, 10, 0, tzinfo=UTC)
    assert item.original_snapshot == STATEMENT
    # 信源/途径归因：新信源记待确认，不入正式池（decision-05）
    assert item.source is not None
    assert item.source.name == "W 公司"
    assert item.source.confirmed is False
    assert item.outlet is not None
    assert item.outlet.name == "渠道大会现场"


def test_reject_when_provenance_incomplete_leaves_no_rows(db_session) -> None:
    proposal = make_proposal(provenance={"source_name": ""})  # 信源归因缺失

    with pytest.raises(ProposalRejectedError) as excinfo:
        StateMachineExecutor().execute(proposal, session=db_session)

    assert any("信源" in reason for reason in excinfo.value.reasons)
    assert db_session.scalars(select(IntelligenceItem)).first() is None
    assert db_session.scalars(select(Source)).first() is None


def test_collects_all_completeness_violations(db_session) -> None:
    proposal = make_proposal(payload={"statement": " "}, rationale="")

    with pytest.raises(ProposalRejectedError) as excinfo:
        StateMachineExecutor().execute(proposal, session=db_session)

    assert "陈述内容缺失" in excinfo.value.reasons
    assert "依据缺失" in excinfo.value.reasons


@pytest.mark.parametrize(
    ("field", "value", "term"),
    [
        ("medium_code", "nonexistent", "媒介"),  # 媒介引用不可解析
        ("modality_code", "nonexistent", "载体"),  # 载体引用不可解析
    ],
)
def test_reject_when_reference_precondition_violated(
    db_session, field: str, value: str, term: str
) -> None:
    proposal = make_proposal(provenance={field: value})

    with pytest.raises(ProposalRejectedError) as excinfo:
        StateMachineExecutor().execute(proposal, session=db_session)

    assert any(term in reason for reason in excinfo.value.reasons)
    assert db_session.scalars(select(IntelligenceItem)).first() is None


def test_reject_when_any_provenance_element_blank(db_session) -> None:
    proposal = make_proposal(
        provenance={"modality_code": "", "medium_code": "", "original_snapshot": ""}
    )

    with pytest.raises(ProposalRejectedError) as excinfo:
        StateMachineExecutor().execute(proposal, session=db_session)

    assert "溯源缺失：载体" in excinfo.value.reasons
    assert "溯源缺失：媒介" in excinfo.value.reasons
    assert "溯源缺失：原文快照" in excinfo.value.reasons


def test_existing_source_and_outlet_are_reused(db_session) -> None:
    first = StateMachineExecutor().execute(make_proposal(), session=db_session)
    second = StateMachineExecutor().execute(make_proposal(), session=db_session)

    assert first.item_id != second.item_id
    assert len(db_session.scalars(select(Source)).unique().all()) == 1
    assert len(db_session.scalars(select(Outlet)).unique().all()) == 1


def test_rejects_unknown_proposal_type(db_session) -> None:
    with pytest.raises(ProposalRejectedError):
        StateMachineExecutor().execute(Proposal(rationale="无类型提案"), session=db_session)
