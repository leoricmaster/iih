"""采集智能体 Collector 单测（doc-06 §3 最简归因）：LLM mock，验证提案组装与调用计量。"""

from datetime import datetime

import pytest
from sqlalchemy import select

from conftest import make_fake_llm
from iih.agents.collector import Collector
from iih.ledger.models import IntelligenceItem, ItemMode, ItemStatus, LlmCall, Source
from iih.ledger.state_machine import StateMachineExecutor

STATEMENT = "W 公司渠道大会：下一代电驱矿卡计划 2027Q2 量产"


def test_manual_submission_builds_lead_proposal_with_metering(db_session, w_attribution) -> None:
    """支撑 IIH-01.01 AC#1：采集智能体归因补记信源与途径，组装线索提案。"""
    collector = Collector(
        llm=make_fake_llm(w_attribution, prompt_tokens=120, completion_tokens=60),
        session=db_session,
        model="deepseek-chat",
    )

    proposal = collector.submit_manual(medium_code="meeting_discussion", statement=STATEMENT)
    result = StateMachineExecutor().execute(proposal, session=db_session)

    item = db_session.get(IntelligenceItem, result.item_id)
    assert item is not None
    assert item.status is ItemStatus.LEAD
    assert item.mode is ItemMode.MANUAL
    assert item.statement == STATEMENT
    assert item.original_snapshot == STATEMENT  # 文字载体：快照 = 提交文本
    assert item.modality.code == "text"
    assert item.medium.code == "meeting_discussion"
    assert isinstance(item.collected_at, datetime)
    assert item.source is not None and item.source.name == "W 公司"
    assert item.source.confirmed is False  # 新信源待确认（decision-05）
    assert item.outlet is not None and item.outlet.name == "渠道大会现场"
    assert proposal.rationale == "陈述主体为 W 公司，发布场景为渠道大会"

    # LLM 调用计量入账：智能体/对象/token/时间/模型
    calls = db_session.scalars(select(LlmCall)).all()
    assert len(calls) == 1
    assert calls[0].agent == "collector"
    assert calls[0].model == "deepseek-chat"
    assert calls[0].prompt_tokens == 120
    assert calls[0].completion_tokens == 60


def test_manual_submission_without_outlet(db_session, w_attribution) -> None:
    attribution = w_attribution.model_copy(update={"outlet_name": None})
    collector = Collector(llm=make_fake_llm(attribution), session=db_session, model="deepseek-chat")

    proposal = collector.submit_manual(medium_code="industry_exchange", statement=STATEMENT)

    assert proposal.provenance.outlet_name is None
    result = StateMachineExecutor().execute(proposal, session=db_session)
    item = db_session.get(IntelligenceItem, result.item_id)
    assert item is not None and item.outlet is None
    assert item.medium.code == "industry_exchange"


def test_manual_submission_rejects_unknown_medium(db_session, fake_llm) -> None:
    collector = Collector(llm=fake_llm, session=db_session, model="deepseek-chat")

    with pytest.raises(ValueError, match="媒介不存在"):
        collector.submit_manual(medium_code="nonexistent", statement=STATEMENT)


def test_reuses_source_across_submissions(db_session, fake_llm) -> None:
    collector = Collector(llm=fake_llm, session=db_session, model="deepseek-chat")
    executor = StateMachineExecutor()
    for statement in (STATEMENT, STATEMENT + "（补充）"):
        executor.execute(
            collector.submit_manual(medium_code="meeting_discussion", statement=statement),
            session=db_session,
        )

    assert len(db_session.scalars(select(Source)).unique().all()) == 1
