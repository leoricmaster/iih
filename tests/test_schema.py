from datetime import UTC, datetime

from sqlalchemy import select

from iih.ledger.models import (
    IntelligenceItem,
    IntelligenceRequirement,
    IntelligenceRequirementStatus,
    ItemMode,
    ItemStatus,
    Medium,
    Modality,
    ProvenanceChainNode,
    RejectionReasonEnum,
    ReviewDecision,
    ReviewDecisionEnum,
    Source,
    SourceType,
    VerificationOutcome,
    VerificationRecord,
)


def test_medium_seed_matches_glossary_closed_set(db_session) -> None:
    codes = set(db_session.scalars(select(Medium.code)))
    assert codes == {
        "internet",
        "user_interview",
        "industry_exhibition",
        "industry_exchange",
        "meeting_discussion",
        "document_reading",
    }


def test_modality_seed_covers_all_carriers(db_session) -> None:
    codes = set(db_session.scalars(select(Modality.code)))
    assert codes == {"webpage", "audio", "text", "image", "document"}


def test_intelligence_item_roundtrip(db_session) -> None:
    medium = db_session.scalars(select(Medium).where(Medium.code == "meeting_discussion")).one()
    modality = db_session.scalars(select(Modality).where(Modality.code == "text")).one()
    source = Source(name="W 公司", type=SourceType.COMPANY, confirmed=False)
    item = IntelligenceItem(
        statement="W 公司渠道大会：下一代电驱矿卡计划 2027Q2 量产",
        status=ItemStatus.LEAD,
        mode=ItemMode.MANUAL,
        medium=medium,
        modality=modality,
        collected_at=datetime(2026, 9, 11, 10, 0, tzinfo=UTC),
        original_snapshot="W 公司渠道大会：下一代电驱矿卡计划 2027Q2 量产",
        source=source,
    )
    db_session.add(item)
    db_session.flush()

    loaded = db_session.get(IntelligenceItem, item.id)
    assert loaded is not None
    assert loaded.status is ItemStatus.LEAD
    assert loaded.mode is ItemMode.MANUAL
    assert loaded.retracted is False
    assert loaded.source is not None and loaded.source.confirmed is False
    assert loaded.medium.name == "会议讨论"
    assert loaded.modality.name == "文字"


def test_intelligence_requirement_roundtrip(db_session) -> None:
    """IIH-01.08：情报需求最简模型落账与状态默认 Draft。"""
    ir = IntelligenceRequirement(name="跟踪 W 公司", content_spec="主题：矿卡、订单、战略")
    db_session.add(ir)
    db_session.flush()

    loaded = db_session.get(IntelligenceRequirement, ir.id)
    assert loaded is not None
    assert loaded.name == "跟踪 W 公司"
    assert loaded.status is IntelligenceRequirementStatus.DRAFT


def test_provenance_chain_node_roundtrip(db_session) -> None:
    """IIH-01.08：转引链节点挂载情报条目，溯源五要素齐备。"""
    medium = db_session.scalars(select(Medium).where(Medium.code == "internet")).one()
    modality = db_session.scalars(select(Modality).where(Modality.code == "webpage")).one()
    source = Source(name="W 公司", type=SourceType.COMPANY, confirmed=True)
    item = IntelligenceItem(
        statement="W 公司公告：与 Z 集团签署合资协议",
        status=ItemStatus.LEAD,
        mode=ItemMode.AUTOMATED,
        medium=medium,
        modality=modality,
        collected_at=datetime(2026, 9, 14, 10, 0, tzinfo=UTC),
        original_snapshot="W 公司公告正文归一化文本",
        source=source,
        content_fingerprint="a" * 64,
        original_url="https://w-mining.example/news",
    )
    db_session.add(item)
    db_session.flush()

    node = ProvenanceChainNode(
        item=item,
        source=source,
        modality=modality,
        medium=medium,
        collected_at=datetime(2026, 9, 14, 10, 0, tzinfo=UTC),
        original_url="https://w-mining.example/news",
    )
    db_session.add(node)
    db_session.flush()

    loaded = db_session.get(ProvenanceChainNode, node.id)
    assert loaded is not None
    assert loaded.item_id == item.id
    assert loaded.source.name == "W 公司"
    assert loaded.medium.code == "internet"
    assert loaded.modality.code == "webpage"


def test_review_decision_roundtrip(db_session) -> None:
    """IIH-01.02：审查决策记录落账（PASS 路径，附依据 + matched_requirement）。"""
    medium = db_session.scalars(select(Medium).where(Medium.code == "internet")).one()
    modality = db_session.scalars(select(Modality).where(Modality.code == "webpage")).one()
    source = Source(name="W 公司", type=SourceType.COMPANY, confirmed=True)
    ir = IntelligenceRequirement(
        name="跟踪 W 公司",
        content_spec="主题：矿卡、订单、战略",
        status=IntelligenceRequirementStatus.ACTIVE,
    )
    item = IntelligenceItem(
        statement="W 公司公告：与 Z 集团签署合资协议",
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

    decision = ReviewDecision(
        item=item,
        decision=ReviewDecisionEnum.PASS,
        reason_type=None,
        matched_requirement_id=ir.id,
        rationale="陈述主题命中激活需求",
    )
    db_session.add(decision)
    db_session.flush()

    loaded = db_session.get(ReviewDecision, decision.id)
    assert loaded is not None
    assert loaded.decision is ReviewDecisionEnum.PASS
    assert loaded.reason_type is None
    assert loaded.matched_requirement_id == ir.id
    assert loaded.rationale == "陈述主题命中激活需求"
    assert loaded.item_id == item.id


def test_review_decision_reject_with_reason(db_session) -> None:
    """IIH-01.02：REJECT 路径落账（reason_type 必填，matched_requirement 为空）。"""
    medium = db_session.scalars(select(Medium).where(Medium.code == "internet")).one()
    modality = db_session.scalars(select(Modality).where(Modality.code == "webpage")).one()
    source = Source(name="W 公司", type=SourceType.COMPANY, confirmed=True)
    item = IntelligenceItem(
        statement="某行业概况：今年市场整体平稳",
        status=ItemStatus.LEAD,
        mode=ItemMode.AUTOMATED,
        medium=medium,
        modality=modality,
        collected_at=datetime(2026, 9, 14, 10, 0, tzinfo=UTC),
        original_snapshot="正文",
        source=source,
    )
    db_session.add(item)
    db_session.flush()

    decision = ReviewDecision(
        item=item,
        decision=ReviewDecisionEnum.REJECT,
        reason_type=RejectionReasonEnum.IRRELEVANT,
        matched_requirement_id=None,
        rationale="陈述与激活需求主题不相关",
    )
    db_session.add(decision)
    db_session.flush()

    loaded = db_session.get(ReviewDecision, decision.id)
    assert loaded is not None
    assert loaded.decision is ReviewDecisionEnum.REJECT
    assert loaded.reason_type is RejectionReasonEnum.IRRELEVANT
    assert loaded.matched_requirement_id is None


def _seed_candidate_item(db_session, *, credit: str | None = "B") -> IntelligenceItem:
    """预置一条 Candidate 态条目 + 单节点转引链，source.credit 可控。"""
    medium = db_session.scalars(select(Medium).where(Medium.code == "internet")).one()
    modality = db_session.scalars(select(Modality).where(Modality.code == "webpage")).one()
    source = Source(name="W 公司", type=SourceType.COMPANY, confirmed=True, credit=credit)
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
    node = ProvenanceChainNode(
        item=item,
        source=source,
        modality=modality,
        medium=medium,
        collected_at=datetime(2026, 9, 14, 10, 0, tzinfo=UTC),
    )
    db_session.add_all([source, item, node])
    db_session.flush()
    return item


def test_verification_record_verified_roundtrip(db_session) -> None:
    """IIH-01.03：核实评级记录落账（VERIFIED 路径，N/R/credibility/rating + 公式版本）。"""
    item = _seed_candidate_item(db_session, credit="B")

    record = VerificationRecord(
        item=item,
        outcome=VerificationOutcome.VERIFIED,
        independent_source_count=1,
        source_reliability="B",
        content_credibility=2,
        rating="B2",
        formula_version="content_credibility_v1",
        rationale="穿透转引链得独立信源 N=1，出处信源可靠度 R=B，公式出内容可信度 2",
    )
    db_session.add(record)
    db_session.flush()

    loaded = db_session.get(VerificationRecord, record.id)
    assert loaded is not None
    assert loaded.outcome is VerificationOutcome.VERIFIED
    assert loaded.independent_source_count == 1
    assert loaded.source_reliability == "B"
    assert loaded.content_credibility == 2
    assert loaded.rating == "B2"
    assert loaded.formula_version == "content_credibility_v1"
    assert loaded.item_id == item.id


def test_verification_record_undetermined_roundtrip(db_session) -> None:
    """IIH-01.03：核实评级记录落账（UNDETERMINED 路径，评级字段为空）。"""
    item = _seed_candidate_item(db_session, credit=None)

    record = VerificationRecord(
        item=item,
        outcome=VerificationOutcome.UNDETERMINED,
        independent_source_count=1,
        source_reliability=None,
        content_credibility=None,
        rating=None,
        formula_version=None,
        rationale="信源画像未设信用档，无法评定内容可信度",
    )
    db_session.add(record)
    db_session.flush()

    loaded = db_session.get(VerificationRecord, record.id)
    assert loaded is not None
    assert loaded.outcome is VerificationOutcome.UNDETERMINED
    assert loaded.independent_source_count == 1
    assert loaded.source_reliability is None
    assert loaded.content_credibility is None
    assert loaded.rating is None
    assert loaded.formula_version is None
