"""采集智能体 Collector 单测（doc-06 §3）：人工提交归因 + 自动拉取 collect_outlet 路径。"""

from datetime import datetime

import pytest
from sqlalchemy import select

from conftest import make_fake_llm, make_fake_llm_extraction
from iih.agents.collector import Collector, StatementExtractionResult
from iih.agents.director import CollectionTask
from iih.ledger.models import (
    IntelligenceItem,
    ItemMode,
    ItemStatus,
    LlmCall,
    Medium,
    Outlet,
    ProvenanceChainNode,
    Source,
    SourceType,
)
from iih.ledger.proposal import (
    IntelligenceItemNewProposal,
    ItemProvenanceAppendProposal,
)
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


# ---- IIH-01.08 自动拉取路径 collect_outlet ----


def _seed_confirmed_w_outlet(db_session) -> Source:
    medium = db_session.scalars(select(Medium).where(Medium.code == "internet")).one()
    source = Source(name="W 公司", type=SourceType.COMPANY, confirmed=True)
    outlet = Outlet(
        source=source, name="官网", entry="https://w-mining.example/news", medium=medium
    )
    db_session.add_all([source, outlet])
    db_session.flush()
    return source


def _make_task(source: Source, outlet: Outlet) -> CollectionTask:
    return CollectionTask(
        requirement_id=1,
        requirement_name="跟踪 W 公司",
        outlet_id=outlet.id,
        source_id=source.id,
        source_name=source.name,
        source_type=source.type,
        outlet_name=outlet.name,
        url="https://w-mining.example/news",
    )


HTML_W_ANNOUNCEMENT = """
<html><head><title>W 公司</title></head><body>
  <nav>导航</nav><header>页头</header>
  <main>
    <p>W 公司公告：与 Z 集团签署合资协议，Q4 设立合资公司。</p>
  </main>
  <footer>页脚</footer><script>var x = 1;</script>
</body></html>
"""


def test_collect_outlet_dedup_miss_calls_llm_and_returns_new_proposal(
    db_session, fake_extraction_llm
) -> None:
    """支撑 IIH-01.08 AC#1：未命中指纹→调 LLM 抽取陈述→产出 AUTOMATED 线索提案。"""
    source, outlet = _seed_confirmed_w_outlet(db_session), None
    outlet = source.outlets[0]
    task = _make_task(source, outlet)
    collector = Collector(llm=fake_extraction_llm, session=db_session, model="deepseek-chat")

    proposal = collector.collect_outlet(task=task, html=HTML_W_ANNOUNCEMENT)

    assert isinstance(proposal, IntelligenceItemNewProposal)
    assert proposal.payload.mode is ItemMode.AUTOMATED
    assert proposal.payload.statement == "W 公司公告：与 Z 集团签署合资协议，Q4 设立合资公司"
    assert (
        proposal.payload.content_fingerprint is not None
        and len(proposal.payload.content_fingerprint) == 64
    )
    assert proposal.payload.original_url == "https://w-mining.example/news"
    assert proposal.provenance.modality_code == "webpage"
    assert proposal.provenance.medium_code == "internet"
    assert proposal.provenance.source_name == "W 公司"
    assert proposal.provenance.outlet_name == "官网"

    # 落账校验
    result = StateMachineExecutor().execute(proposal, session=db_session)
    item = db_session.get(IntelligenceItem, result.item_id)
    assert item is not None
    assert item.status is ItemStatus.LEAD
    assert item.mode is ItemMode.AUTOMATED
    assert item.modality.code == "webpage"
    assert item.medium.code == "internet"
    assert item.source.name == "W 公司"
    assert item.outlet.name == "官网"
    assert item.original_url == "https://w-mining.example/news"

    # LLM 调用计量入账
    calls = db_session.scalars(select(LlmCall)).all()
    assert len(calls) == 1
    assert calls[0].target == "outlet_collection"


def test_collect_outlet_dedup_hit_returns_append_proposal_without_llm(
    db_session, fake_extraction_llm, w_extraction
) -> None:
    """支撑 IIH-01.08 AC#2：指纹命中既有条目→返回追加提案，不调 LLM、不计量。"""
    source = _seed_confirmed_w_outlet(db_session)
    outlet = source.outlets[0]
    task = _make_task(source, outlet)
    collector = Collector(llm=fake_extraction_llm, session=db_session, model="deepseek-chat")

    # 首次拉取：落账一条
    first = collector.collect_outlet(task=task, html=HTML_W_ANNOUNCEMENT)
    assert isinstance(first, IntelligenceItemNewProposal)
    StateMachineExecutor().execute(first, session=db_session)
    llm_calls_after_first = len(db_session.scalars(select(LlmCall)).all())

    # 第二次拉取同内容（不同信源模拟转载）：指纹命中
    media_source = Source(name="行业媒体 A", type=SourceType.MEDIA, confirmed=True)
    db_session.add(media_source)
    db_session.flush()
    repost_task = CollectionTask(
        requirement_id=1,
        requirement_name="跟踪",
        outlet_id=outlet.id,  # 占位，不影响测试
        source_id=media_source.id,
        source_name="行业媒体 A",
        source_type=SourceType.MEDIA,
        outlet_name=None,
        url="https://media-a.example/repost",
    )

    proposal = collector.collect_outlet(task=repost_task, html=HTML_W_ANNOUNCEMENT)

    assert isinstance(proposal, ItemProvenanceAppendProposal)
    assert proposal.payload.source_name == "行业媒体 A"
    assert proposal.payload.original_url == "https://media-a.example/repost"
    # 不调 LLM、不计量
    assert len(db_session.scalars(select(LlmCall)).all()) == llm_calls_after_first

    # 落账校验：追加节点，不新建条目
    items_before = len(db_session.scalars(select(IntelligenceItem)).all())
    StateMachineExecutor().execute(proposal, session=db_session)
    items_after = len(db_session.scalars(select(IntelligenceItem)).all())
    assert items_after == items_before  # 不新增条目

    nodes = db_session.scalars(select(ProvenanceChainNode)).all()
    assert len(nodes) == 2  # 初始节点 + 追加节点
    appended = next(n for n in nodes if n.source.name == "行业媒体 A")
    assert appended.original_url == "https://media-a.example/repost"


def test_collect_outlet_llm_no_statement_returns_none(db_session, fake_extraction_llm) -> None:
    """LLM 判定无情报价值内容→返回 None，不产出提案，计量已发生。"""
    source = _seed_confirmed_w_outlet(db_session)
    outlet = source.outlets[0]
    task = _make_task(source, outlet)

    empty_extraction = StatementExtractionResult(statement="", rationale="页面无情报价值内容")
    collector = Collector(
        llm=make_fake_llm_extraction(empty_extraction), session=db_session, model="deepseek-chat"
    )

    proposal = collector.collect_outlet(task=task, html="<html><body>关于我们</body></html>")

    assert proposal is None
    # 计量已发生（LLM 成本在调用时已发生）
    assert len(db_session.scalars(select(LlmCall)).all()) == 1
