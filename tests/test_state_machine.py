"""状态机执行器单测：通过落账 / 溯源缺失驳回 / 前置违反驳回（plan 阶段 3）。"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from iih.ledger.models import (
    IntelligenceItem,
    IntelligenceRequirement,
    IntelligenceRequirementStatus,
    ItemMode,
    ItemStatus,
    Outlet,
    ProvenanceChainNode,
    RejectionReasonEnum,
    ReviewDecision,
    ReviewDecisionEnum,
    Source,
    SourceType,
)
from iih.ledger.proposal import (
    IntelligenceItemNewPayload,
    IntelligenceItemNewProposal,
    IntelligenceRequirementActivatePayload,
    IntelligenceRequirementActivateProposal,
    IntelligenceRequirementRegisterPayload,
    IntelligenceRequirementRegisterProposal,
    ItemProvenanceAppendPayload,
    ItemProvenanceAppendProposal,
    Proposal,
    ProvenanceData,
    ReviewPayload,
    ReviewProposal,
    SourceRegisterPayload,
    SourceRegisterProposal,
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


# ---- IIH-01.07 种子信源登记 ----


def make_register_proposal(**overrides) -> SourceRegisterProposal:
    """构造一份字段齐备的「种子信源登记」提案；kwargs 覆盖用于制造缺陷。"""
    payload_fields = {
        "source_name": "W 公司",
        "source_type": SourceType.COMPANY,
        "outlet_name": "官网",
        "outlet_entry": "https://w-mining.example/news",
    } | overrides.pop("payload", {})
    top_fields = {"rationale": "人工登记（decision-05 通道一）"} | overrides
    return SourceRegisterProposal(payload=SourceRegisterPayload(**payload_fields), **top_fields)


def test_source_register_lands_confirmed_with_internet_outlet(db_session) -> None:
    """支撑 IIH-01.07 AC#1：登记落账 confirmed=True、credit=None、途径挂 internet。"""
    result = StateMachineExecutor().execute(make_register_proposal(), session=db_session)

    assert result.source_id is not None
    source = db_session.get(Source, result.source_id)
    assert source is not None
    assert source.name == "W 公司"
    assert source.type is SourceType.COMPANY
    assert source.confirmed is True
    assert source.credit is None  # 信用档由 IIH-01.06 信用计算器首次更新时设
    assert len(source.outlets) == 1
    outlet = source.outlets[0]
    assert outlet.name == "官网"
    assert outlet.entry == "https://w-mining.example/news"
    assert outlet.medium.code == "internet"


def test_source_register_rejects_blank_fields(db_session) -> None:
    """支撑 IIH-01.07 AC#2：记账层字段完整性校验，缺失即驳回、无落账。"""
    proposal = make_register_proposal(
        payload={"source_name": " ", "outlet_name": " ", "outlet_entry": " "},
        rationale=" ",
    )

    with pytest.raises(ProposalRejectedError) as excinfo:
        StateMachineExecutor().execute(proposal, session=db_session)

    assert "主体名称缺失" in excinfo.value.reasons
    assert "途径名缺失" in excinfo.value.reasons
    assert "采集入口缺失" in excinfo.value.reasons
    assert "依据缺失" in excinfo.value.reasons
    assert db_session.scalars(select(Source)).first() is None
    assert db_session.scalars(select(Outlet)).first() is None


def test_source_register_rejects_duplicate_source_name(db_session) -> None:
    StateMachineExecutor().execute(make_register_proposal(), session=db_session)

    with pytest.raises(ProposalRejectedError) as excinfo:
        StateMachineExecutor().execute(
            make_register_proposal(payload={"outlet_name": "公众号"}), session=db_session
        )

    assert any("信源名已存在" in reason for reason in excinfo.value.reasons)
    sources = db_session.scalars(select(Source).where(Source.name == "W 公司")).unique().all()
    assert len(sources) == 1  # 不新增重复信源


def test_source_register_rejects_when_internet_medium_missing(db_session) -> None:
    """媒介引用不可解析：internet seed 缺失时驳回（环境异常兜底）。"""
    from iih.ledger.models import Medium

    db_session.query(Medium).where(Medium.code == "internet").delete()
    db_session.flush()

    with pytest.raises(ProposalRejectedError) as excinfo:
        StateMachineExecutor().execute(make_register_proposal(), session=db_session)

    assert any("internet" in reason for reason in excinfo.value.reasons)
    assert db_session.scalars(select(Source)).first() is None


# ---- IIH-01.08 互联网信源自动拉取 ----


def make_automated_proposal(**overrides) -> IntelligenceItemNewProposal:
    """AUTOMATED 模式提案：信源与途径须已登记 confirmed=True。"""
    provenance_fields = {
        "modality_code": "webpage",
        "medium_code": "internet",
        "collected_at": datetime(2026, 9, 14, 10, 0, tzinfo=UTC),
        "original_snapshot": "W 公司公告正文归一化文本",
        "source_name": "W 公司",
        "source_type": SourceType.COMPANY,
        "outlet_name": "官网",
    } | overrides.pop("provenance", {})
    payload_fields = {
        "statement": "W 公司公告：与 Z 集团签署合资协议",
        "mode": ItemMode.AUTOMATED,
        "content_fingerprint": "a" * 64,
        "original_url": "https://w-mining.example/news",
    } | overrides.pop("payload", {})
    top_fields = {"rationale": "自动拉取，抽取自页面正文"} | overrides
    return IntelligenceItemNewProposal(
        payload=IntelligenceItemNewPayload(**payload_fields),
        provenance=ProvenanceData(**provenance_fields),
        **top_fields,
    )


def seed_confirmed_w_outlet(db_session) -> Source:
    """预置已登记信源 W 公司 + 互联网途径官网。"""
    from iih.ledger.models import Medium

    medium = db_session.scalars(select(Medium).where(Medium.code == "internet")).one()
    source = Source(name="W 公司", type=SourceType.COMPANY, confirmed=True)
    outlet = Outlet(
        source=source, name="官网", entry="https://w-mining.example/news", medium=medium
    )
    db_session.add_all([source, outlet])
    db_session.flush()
    return source


def test_automated_item_new_lands_lead_with_fingerprint_and_initial_node(db_session) -> None:
    """支撑 IIH-01.08 AC#1：自动拉取落账 Lead + 内容指纹 + 初始转引链节点。"""
    seed_confirmed_w_outlet(db_session)

    result = StateMachineExecutor().execute(make_automated_proposal(), session=db_session)

    item = db_session.get(IntelligenceItem, result.item_id)
    assert item is not None
    assert item.status is ItemStatus.LEAD
    assert item.mode is ItemMode.AUTOMATED
    assert item.modality.code == "webpage"
    assert item.medium.code == "internet"
    assert item.source is not None and item.source.name == "W 公司"
    assert item.source.confirmed is True
    assert item.outlet is not None and item.outlet.name == "官网"
    assert item.content_fingerprint == "a" * 64
    assert item.original_url == "https://w-mining.example/news"

    # 初始转引链节点：出处信源即首节点
    nodes = db_session.scalars(
        select(ProvenanceChainNode).where(ProvenanceChainNode.item_id == item.id)
    ).all()
    assert len(nodes) == 1
    assert nodes[0].source.name == "W 公司"
    assert nodes[0].outlet.name == "官网"


def test_automated_item_new_rejects_unconfirmed_source(db_session) -> None:
    """AUTOMATED 模式：信源未 confirmed 驳回（保护已登记信源边界）。"""
    source = Source(name="W 公司", type=SourceType.COMPANY, confirmed=False)
    db_session.add(source)
    db_session.flush()

    with pytest.raises(ProposalRejectedError) as excinfo:
        StateMachineExecutor().execute(make_automated_proposal(), session=db_session)

    assert any("未确认" in r for r in excinfo.value.reasons)
    assert db_session.scalars(select(IntelligenceItem)).first() is None


def test_automated_item_new_rejects_unknown_source(db_session) -> None:
    """AUTOMATED 模式：信源未登记驳回。"""
    with pytest.raises(ProposalRejectedError) as excinfo:
        StateMachineExecutor().execute(make_automated_proposal(), session=db_session)

    assert any("未登记" in r for r in excinfo.value.reasons)


def test_automated_item_new_rejects_unknown_outlet(db_session) -> None:
    """AUTOMATED 模式：途径未登记驳回。"""
    source = Source(name="W 公司", type=SourceType.COMPANY, confirmed=True)
    db_session.add(source)
    db_session.flush()

    with pytest.raises(ProposalRejectedError) as excinfo:
        StateMachineExecutor().execute(make_automated_proposal(), session=db_session)

    assert any("途径未登记" in r for r in excinfo.value.reasons)


def test_ir_register_lands_draft(db_session) -> None:
    """情报需求登记：落账 Draft。"""
    proposal = IntelligenceRequirementRegisterProposal(
        payload=IntelligenceRequirementRegisterPayload(
            name="跟踪 W 公司", content_spec="主题：矿卡、订单、战略"
        ),
        rationale="消费方声明",
    )

    result = StateMachineExecutor().execute(proposal, session=db_session)

    ir = db_session.get(IntelligenceRequirement, result.requirement_id)
    assert ir is not None
    assert ir.name == "跟踪 W 公司"
    assert ir.status is IntelligenceRequirementStatus.DRAFT


def test_ir_register_rejects_blank_fields(db_session) -> None:
    """情报需求登记：字段缺失驳回。"""
    proposal = IntelligenceRequirementRegisterProposal(
        payload=IntelligenceRequirementRegisterPayload(name=" ", content_spec=" "),
        rationale=" ",
    )

    with pytest.raises(ProposalRejectedError) as excinfo:
        StateMachineExecutor().execute(proposal, session=db_session)

    assert "需求名称缺失" in excinfo.value.reasons
    assert "内容规格缺失" in excinfo.value.reasons
    assert "依据缺失" in excinfo.value.reasons
    assert db_session.scalars(select(IntelligenceRequirement)).first() is None


def test_ir_activate_transitions_draft_to_active(db_session) -> None:
    """情报需求激活：Draft → Active。"""
    ir = IntelligenceRequirement(name="跟踪 W 公司", content_spec="主题：矿卡")
    db_session.add(ir)
    db_session.flush()

    result = StateMachineExecutor().execute(
        IntelligenceRequirementActivateProposal(
            payload=IntelligenceRequirementActivatePayload(requirement_id=ir.id),
            rationale="消费方确认激活",
        ),
        session=db_session,
    )

    assert result.requirement_id == ir.id
    assert (
        db_session.get(IntelligenceRequirement, ir.id).status
        is IntelligenceRequirementStatus.ACTIVE
    )


def test_ir_activate_rejects_non_draft_state(db_session) -> None:
    """情报需求激活：非 Draft 前置违反驳回。"""
    ir = IntelligenceRequirement(
        name="跟踪 W 公司", content_spec="主题", status=IntelligenceRequirementStatus.ACTIVE
    )
    db_session.add(ir)
    db_session.flush()

    with pytest.raises(ProposalRejectedError) as excinfo:
        StateMachineExecutor().execute(
            IntelligenceRequirementActivateProposal(
                payload=IntelligenceRequirementActivatePayload(requirement_id=ir.id),
                rationale="x",
            ),
            session=db_session,
        )

    assert any("前置违反" in r for r in excinfo.value.reasons)
    assert (
        db_session.get(IntelligenceRequirement, ir.id).status
        is IntelligenceRequirementStatus.ACTIVE
    )


def test_ir_activate_rejects_unknown_requirement(db_session) -> None:
    with pytest.raises(ProposalRejectedError) as excinfo:
        StateMachineExecutor().execute(
            IntelligenceRequirementActivateProposal(
                payload=IntelligenceRequirementActivatePayload(requirement_id=9999),
                rationale="x",
            ),
            session=db_session,
        )

    assert "情报需求不存在" in excinfo.value.reasons


def test_item_provenance_append_lands_node(db_session) -> None:
    """支撑 IIH-01.08 AC#2：指纹命中追加转引链节点。"""
    seed_confirmed_w_outlet(db_session)
    # 先落账一条自动拉取条目（出处信源 = W 公司·官网）
    first = StateMachineExecutor().execute(make_automated_proposal(), session=db_session)
    item = db_session.get(IntelligenceItem, first.item_id)

    # 模拟另一信源「行业媒体 A」转载同内容，指纹命中
    media_source = Source(name="行业媒体 A", type=SourceType.MEDIA, confirmed=True)
    db_session.add(media_source)
    db_session.flush()

    proposal = ItemProvenanceAppendProposal(
        payload=ItemProvenanceAppendPayload(
            item_id=item.id,
            source_name="行业媒体 A",
            source_type=SourceType.MEDIA,
            outlet_name=None,
            original_url="https://media-a.example/repost",
            collected_at=datetime(2026, 9, 14, 11, 0, tzinfo=UTC),
        ),
        rationale="指纹命中追加转引链节点",
    )

    StateMachineExecutor().execute(proposal, session=db_session)

    nodes = db_session.scalars(
        select(ProvenanceChainNode).where(ProvenanceChainNode.item_id == item.id)
    ).all()
    assert len(nodes) == 2  # 初始节点 + 追加节点
    appended = next(n for n in nodes if n.source.name == "行业媒体 A")
    assert appended.original_url == "https://media-a.example/repost"


def test_item_provenance_append_rejects_unknown_item(db_session) -> None:
    seed_confirmed_w_outlet(db_session)

    with pytest.raises(ProposalRejectedError) as excinfo:
        StateMachineExecutor().execute(
            ItemProvenanceAppendProposal(
                payload=ItemProvenanceAppendPayload(
                    item_id=9999,
                    source_name="W 公司",
                    source_type=SourceType.COMPANY,
                    collected_at=datetime(2026, 9, 14, 11, 0, tzinfo=UTC),
                ),
                rationale="x",
            ),
            session=db_session,
        )

    assert "情报条目不存在" in excinfo.value.reasons


def test_item_provenance_append_rejects_duplicate_node(db_session) -> None:
    """同(item, source, outlet)节点不重复追加。"""
    seed_confirmed_w_outlet(db_session)
    first = StateMachineExecutor().execute(make_automated_proposal(), session=db_session)
    item = db_session.get(IntelligenceItem, first.item_id)

    with pytest.raises(ProposalRejectedError) as excinfo:
        StateMachineExecutor().execute(
            ItemProvenanceAppendProposal(
                payload=ItemProvenanceAppendPayload(
                    item_id=item.id,
                    source_name="W 公司",
                    source_type=SourceType.COMPANY,
                    outlet_name="官网",
                    original_url="https://w-mining.example/news",
                    collected_at=datetime(2026, 9, 14, 11, 0, tzinfo=UTC),
                ),
                rationale="x",
            ),
            session=db_session,
        )

    assert "转引链节点已存在" in excinfo.value.reasons


# ---- IIH-01.02 线索审查过滤 ----


def _seed_lead_with_active_ir(db_session) -> tuple[IntelligenceItem, IntelligenceRequirement]:
    """预置一条 Lead 态条目 + 激活情报需求，返回 (item, ir)。"""
    from iih.ledger.models import Medium, Modality

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
    return item, ir


def test_review_pass_transitions_lead_to_candidate(db_session) -> None:
    """支撑 IIH-01.02 AC#1：通过决策 Lead → Candidate + ReviewDecision 落账。"""
    item, ir = _seed_lead_with_active_ir(db_session)

    result = StateMachineExecutor().execute(
        ReviewProposal(
            payload=ReviewPayload(
                item_id=item.id,
                decision=ReviewDecisionEnum.PASS,
                reason_type=None,
                matched_requirement_id=ir.id,
            ),
            rationale="陈述主题命中激活需求",
        ),
        session=db_session,
    )

    assert result.item_id == item.id
    refreshed = db_session.get(IntelligenceItem, item.id)
    assert refreshed is not None
    assert refreshed.status is ItemStatus.CANDIDATE

    decisions = db_session.scalars(
        select(ReviewDecision).where(ReviewDecision.item_id == item.id)
    ).all()
    assert len(decisions) == 1
    assert decisions[0].decision is ReviewDecisionEnum.PASS
    assert decisions[0].reason_type is None
    assert decisions[0].matched_requirement_id == ir.id
    assert decisions[0].rationale == "陈述主题命中激活需求"


def test_review_reject_transitions_lead_to_noise(db_session) -> None:
    """支撑 IIH-01.02 AC#2：否决决策 Lead → Noise + ReviewDecision 附理由落账。"""
    item, _ir = _seed_lead_with_active_ir(db_session)

    StateMachineExecutor().execute(
        ReviewProposal(
            payload=ReviewPayload(
                item_id=item.id,
                decision=ReviewDecisionEnum.REJECT,
                reason_type=RejectionReasonEnum.IRRELEVANT,
                matched_requirement_id=None,
            ),
            rationale="陈述与激活需求主题不相关",
        ),
        session=db_session,
    )

    refreshed = db_session.get(IntelligenceItem, item.id)
    assert refreshed is not None
    assert refreshed.status is ItemStatus.NOISE

    decisions = db_session.scalars(
        select(ReviewDecision).where(ReviewDecision.item_id == item.id)
    ).all()
    assert len(decisions) == 1
    assert decisions[0].decision is ReviewDecisionEnum.REJECT
    assert decisions[0].reason_type is RejectionReasonEnum.IRRELEVANT
    assert decisions[0].matched_requirement_id is None
    assert decisions[0].rationale == "陈述与激活需求主题不相关"


def test_review_rejects_non_lead_state(db_session) -> None:
    """前置违反：非 Lead 态不可审查。"""
    item, ir = _seed_lead_with_active_ir(db_session)
    item.status = ItemStatus.CANDIDATE
    db_session.flush()

    with pytest.raises(ProposalRejectedError) as excinfo:
        StateMachineExecutor().execute(
            ReviewProposal(
                payload=ReviewPayload(
                    item_id=item.id,
                    decision=ReviewDecisionEnum.PASS,
                    matched_requirement_id=ir.id,
                ),
                rationale="x",
            ),
            session=db_session,
        )

    assert any("前置违反" in r for r in excinfo.value.reasons)
    # 状态不变
    assert db_session.get(IntelligenceItem, item.id).status is ItemStatus.CANDIDATE


def test_review_rejects_unknown_item(db_session) -> None:
    with pytest.raises(ProposalRejectedError) as excinfo:
        StateMachineExecutor().execute(
            ReviewProposal(
                payload=ReviewPayload(
                    item_id=9999,
                    decision=ReviewDecisionEnum.REJECT,
                    reason_type=RejectionReasonEnum.IRRELEVANT,
                ),
                rationale="x",
            ),
            session=db_session,
        )

    assert "情报条目不存在" in excinfo.value.reasons


def test_review_rejects_blank_rationale(db_session) -> None:
    item, ir = _seed_lead_with_active_ir(db_session)

    with pytest.raises(ProposalRejectedError) as excinfo:
        StateMachineExecutor().execute(
            ReviewProposal(
                payload=ReviewPayload(
                    item_id=item.id,
                    decision=ReviewDecisionEnum.PASS,
                    matched_requirement_id=ir.id,
                ),
                rationale=" ",
            ),
            session=db_session,
        )

    assert "依据缺失" in excinfo.value.reasons


def test_review_pass_rejects_without_matched_requirement(db_session) -> None:
    """PASS 决策必须填 matched_requirement_id。"""
    item, _ir = _seed_lead_with_active_ir(db_session)

    with pytest.raises(ProposalRejectedError) as excinfo:
        StateMachineExecutor().execute(
            ReviewProposal(
                payload=ReviewPayload(
                    item_id=item.id,
                    decision=ReviewDecisionEnum.PASS,
                    matched_requirement_id=None,
                ),
                rationale="x",
            ),
            session=db_session,
        )

    assert "通过决策缺少匹配的情报需求" in excinfo.value.reasons


def test_review_reject_rejects_without_reason_type(db_session) -> None:
    """REJECT 决策必须填 reason_type。"""
    item, _ir = _seed_lead_with_active_ir(db_session)

    with pytest.raises(ProposalRejectedError) as excinfo:
        StateMachineExecutor().execute(
            ReviewProposal(
                payload=ReviewPayload(
                    item_id=item.id,
                    decision=ReviewDecisionEnum.REJECT,
                    reason_type=None,
                ),
                rationale="x",
            ),
            session=db_session,
        )

    assert "否决决策缺少理由类型" in excinfo.value.reasons


def test_review_pass_rejects_unknown_requirement(db_session) -> None:
    """PASS 时 matched_requirement 不存在驳回。"""
    item, _ir = _seed_lead_with_active_ir(db_session)

    with pytest.raises(ProposalRejectedError) as excinfo:
        StateMachineExecutor().execute(
            ReviewProposal(
                payload=ReviewPayload(
                    item_id=item.id,
                    decision=ReviewDecisionEnum.PASS,
                    matched_requirement_id=9999,
                ),
                rationale="x",
            ),
            session=db_session,
        )

    assert "匹配的情报需求不存在" in excinfo.value.reasons


def test_review_pass_rejects_non_active_requirement(db_session) -> None:
    """PASS 时 matched_requirement 非 ACTIVE 驳回（如 Draft / Paused / Closed）。"""
    from iih.ledger.models import Medium, Modality

    medium = db_session.scalars(select(Medium).where(Medium.code == "internet")).one()
    modality = db_session.scalars(select(Modality).where(Modality.code == "webpage")).one()
    source = Source(name="W 公司", type=SourceType.COMPANY, confirmed=True)
    ir = IntelligenceRequirement(
        name="跟踪 W 公司",
        content_spec="主题",
        status=IntelligenceRequirementStatus.DRAFT,
    )
    item = IntelligenceItem(
        statement="陈述",
        status=ItemStatus.LEAD,
        mode=ItemMode.AUTOMATED,
        medium=medium,
        modality=modality,
        collected_at=datetime(2026, 9, 14, 10, 0, tzinfo=UTC),
        original_snapshot="x",
        source=source,
    )
    db_session.add_all([ir, item])
    db_session.flush()

    with pytest.raises(ProposalRejectedError) as excinfo:
        StateMachineExecutor().execute(
            ReviewProposal(
                payload=ReviewPayload(
                    item_id=item.id,
                    decision=ReviewDecisionEnum.PASS,
                    matched_requirement_id=ir.id,
                ),
                rationale="x",
            ),
            session=db_session,
        )

    assert any("非激活态" in r for r in excinfo.value.reasons)
