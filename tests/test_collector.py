"""采集智能体 Collector 单测（doc-06 §3）：人工提交归因 + 自动拉取两跳路径。"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from conftest import (
    FakeSnapshotStore,
    make_fake_llm,
    make_fake_llm_collect,
    make_selection_article,
    make_selection_self,
)
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
from iih.tools.html_normalize import fingerprint, normalize

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
    assert item.snapshot_object_key is None
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


# ---- 自动拉取两跳路径 collect_outlet（IIH-01.15） ----


ENTRY_URL = "https://w-mining.example/news"
ARTICLE_URL = "https://w-mining.example/news/2026/jv-agreement"

ENTRY_LISTING_HTML = """
<html><body>
  <nav><a href="/">首页</a><a href="/products">产品</a></nav>
  <main>
    <h1>新闻</h1>
    <a href="/news/2026/jv-agreement">W 公司与 Z 集团签署合资协议</a>
  </main>
</body></html>
"""

ARTICLE_HTML = """
<html><head><title>W 公司</title></head><body>
  <nav>导航</nav><header>页头</header>
  <main>
    <p>W 公司公告：与 Z 集团签署合资协议，Q4 设立合资公司。</p>
  </main>
  <footer>页脚</footer><script>var x = 1;</script>
</body></html>
"""


def _seed_confirmed_w_outlet(db_session) -> Source:
    medium = db_session.scalars(select(Medium).where(Medium.code == "internet")).one()
    source = Source(name="W 公司", type=SourceType.COMPANY, confirmed=True)
    outlet = Outlet(source=source, name="官网", entry=ENTRY_URL, medium=medium)
    db_session.add_all([source, outlet])
    db_session.flush()
    return source


def _make_task(source: Source, outlet: Outlet, url: str = ENTRY_URL) -> CollectionTask:
    return CollectionTask(
        requirement_id=1,
        requirement_name="跟踪 W 公司",
        outlet_id=outlet.id,
        source_id=source.id,
        source_name=source.name,
        source_type=source.type,
        outlet_name=outlet.name,
        url=url,
    )


def _fetch_pages(pages: dict[str, str]):
    """fetch_article 替身：仅允许抓取预置页面（未预置即意外抓取，测试失败）。"""

    def fetch(url: str) -> str:
        assert url in pages, f"意外抓取：{url}"
        return pages[url]

    return fetch


def test_collect_two_hop_extracts_from_article_page(db_session) -> None:
    """对应 IIH-01.15 AC#1：列表页选链→抓文章页→陈述抽自文章页，原文 URL 与快照均锚定文章页。"""
    source = _seed_confirmed_w_outlet(db_session)
    task = _make_task(source, source.outlets[0])
    extraction = StatementExtractionResult(
        statement="W 公司公告：与 Z 集团签署合资协议，Q4 设立合资公司",
        rationale="文章公告段主体陈述",
    )
    store = FakeSnapshotStore()
    collector = Collector(
        llm=make_fake_llm_collect(make_selection_article(), extraction),
        session=db_session,
        model="deepseek-chat",
    )

    proposal = collector.collect_outlet(
        task=task,
        html=ENTRY_LISTING_HTML,
        fetch_article=_fetch_pages({ARTICLE_URL: ARTICLE_HTML}),
        store=store,
    )

    assert isinstance(proposal, IntelligenceItemNewProposal)
    assert proposal.payload.mode is ItemMode.AUTOMATED
    assert proposal.payload.original_url == ARTICLE_URL  # 实际抓取地址，非入口页
    assert proposal.payload.content_fingerprint == fingerprint(normalize(ARTICLE_HTML))
    assert proposal.payload.snapshot_object_key == store.put_html(ARTICLE_HTML)
    assert proposal.provenance.original_snapshot is None  # 归一化文本不再作为快照
    assert store.objects[proposal.payload.snapshot_object_key] == ARTICLE_HTML

    result = StateMachineExecutor().execute(proposal, session=db_session)
    item = db_session.get(IntelligenceItem, result.item_id)
    assert item is not None
    assert item.status is ItemStatus.LEAD
    assert item.original_url == ARTICLE_URL
    assert item.snapshot_object_key is not None
    assert item.original_snapshot is None

    # 计量：选链 + 抽取两次 LLM
    calls = db_session.scalars(select(LlmCall)).all()
    assert [c.target for c in calls] == ["outlet_link_select", "outlet_collection"]


def test_collect_extracts_event_time(db_session) -> None:
    """抽取输出事件时间（naive）→ 提案按 UTC aware 落账条目事件时间（doc-03 事件时间）。"""
    source = _seed_confirmed_w_outlet(db_session)
    task = _make_task(source, source.outlets[0])
    extraction = StatementExtractionResult(
        statement="W 公司公告：与 Z 集团签署合资协议，Q4 设立合资公司",
        event_time=datetime(2026, 8, 30),
        rationale="文章公告段主体陈述",
    )
    collector = Collector(
        llm=make_fake_llm_collect(make_selection_article(), extraction),
        session=db_session,
        model="deepseek-chat",
    )
    proposal = collector.collect_outlet(
        task=task,
        html=ENTRY_LISTING_HTML,
        fetch_article=_fetch_pages({ARTICLE_URL: ARTICLE_HTML}),
        store=FakeSnapshotStore(),
    )

    assert proposal.payload.event_time == datetime(2026, 8, 30, tzinfo=UTC)

    result = StateMachineExecutor().execute(proposal, session=db_session)
    item = db_session.get(IntelligenceItem, result.item_id)
    assert item.event_time == datetime(2026, 8, 30, tzinfo=UTC)


def test_collect_single_hop_when_entry_is_article(db_session) -> None:
    """对应 IIH-01.15 AC#3：入口页即文章页（选链判空）→ 单跳回退，URL 为入口地址。"""
    source = _seed_confirmed_w_outlet(db_session)
    task = _make_task(source, source.outlets[0])
    extraction = StatementExtractionResult(
        statement="W 公司公告：与 Z 集团签署合资协议，Q4 设立合资公司",
        rationale="页面公告区主体陈述",
    )
    store = FakeSnapshotStore()
    collector = Collector(
        llm=make_fake_llm_collect(make_selection_self(), extraction),
        session=db_session,
        model="deepseek-chat",
    )

    proposal = collector.collect_outlet(
        task=task,
        html=ARTICLE_HTML,
        fetch_article=_fetch_pages({}),  # 单跳：不得发起第二跳抓取
        store=store,
    )

    assert isinstance(proposal, IntelligenceItemNewProposal)
    assert proposal.payload.original_url == ENTRY_URL
    assert proposal.payload.snapshot_object_key == store.put_html(ARTICLE_HTML)


def test_collect_url_dedup_appends_node_without_refetch(db_session) -> None:
    """对应 IIH-01.15 AC#2：选链命中已采 URL → 不抓文章页、不调抽取，仅追加节点。"""
    source = _seed_confirmed_w_outlet(db_session)
    task = _make_task(source, source.outlets[0])
    extraction = StatementExtractionResult(
        statement="W 公司公告：与 Z 集团签署合资协议，Q4 设立合资公司",
        rationale="文章公告段主体陈述",
    )
    store = FakeSnapshotStore()
    collector = Collector(
        llm=make_fake_llm_collect(make_selection_article(), extraction),
        session=db_session,
        model="deepseek-chat",
    )

    first = collector.collect_outlet(
        task=task,
        html=ENTRY_LISTING_HTML,
        fetch_article=_fetch_pages({ARTICLE_URL: ARTICLE_HTML}),
        store=store,
    )
    assert isinstance(first, IntelligenceItemNewProposal)
    StateMachineExecutor().execute(first, session=db_session)
    llm_calls_after_first = len(db_session.scalars(select(LlmCall)).all())

    # 同一途径再次拉到同一文章：URL 级去重，节点已存在 → None（无新内容）
    again = collector.collect_outlet(
        task=task,
        html=ENTRY_LISTING_HTML,
        fetch_article=_fetch_pages({}),  # 不得再抓文章页
        store=store,
    )
    assert again is None
    # 仅选链一次 LLM，无抽取
    calls = db_session.scalars(select(LlmCall)).all()
    assert len(calls) == llm_calls_after_first + 1
    assert calls[-1].target == "outlet_link_select"


def test_collect_url_dedup_other_source_appends_node(db_session) -> None:
    """选链命中已采 URL（他源转载场景）→ 追加该信源节点。"""
    source = _seed_confirmed_w_outlet(db_session)
    task = _make_task(source, source.outlets[0])
    extraction = StatementExtractionResult(
        statement="W 公司公告：与 Z 集团签署合资协议，Q4 设立合资公司",
        rationale="文章公告段主体陈述",
    )
    collector = Collector(
        llm=make_fake_llm_collect(make_selection_article(), extraction),
        session=db_session,
        model="deepseek-chat",
    )
    first = collector.collect_outlet(
        task=task,
        html=ENTRY_LISTING_HTML,
        fetch_article=_fetch_pages({ARTICLE_URL: ARTICLE_HTML}),
        store=FakeSnapshotStore(),
    )
    assert isinstance(first, IntelligenceItemNewProposal)
    StateMachineExecutor().execute(first, session=db_session)

    media_source = Source(name="行业媒体 A", type=SourceType.MEDIA, confirmed=True)
    db_session.add(media_source)
    db_session.flush()
    media_entry = "https://media-a.example/news"
    media_task = CollectionTask(
        requirement_id=1,
        requirement_name="跟踪",
        outlet_id=source.outlets[0].id,  # 占位，不影响测试
        source_id=media_source.id,
        source_name="行业媒体 A",
        source_type=SourceType.MEDIA,
        outlet_name=None,
        url=media_entry,
    )

    proposal = collector.collect_outlet(
        task=media_task,
        html=ENTRY_LISTING_HTML,  # 列表同样指向该文章
        fetch_article=_fetch_pages({}),  # URL 命中：不抓文章页
        store=FakeSnapshotStore(),
    )

    assert isinstance(proposal, ItemProvenanceAppendProposal)
    assert proposal.payload.source_name == "行业媒体 A"
    assert proposal.payload.original_url == ARTICLE_URL

    items_before = len(db_session.scalars(select(IntelligenceItem)).all())
    StateMachineExecutor().execute(proposal, session=db_session)
    assert len(db_session.scalars(select(IntelligenceItem)).all()) == items_before
    nodes = db_session.scalars(select(ProvenanceChainNode)).all()
    assert len(nodes) == 2  # 初始节点 + 媒体转载节点
    assert any(n.source.name == "行业媒体 A" and n.original_url == ARTICLE_URL for n in nodes)


def test_collect_fingerprint_dedup_on_article_text_appends(db_session) -> None:
    """指纹级去重（文章页文本）：不同 URL 同内容 → 追加节点（URL 不同，指纹命中）。"""
    source = _seed_confirmed_w_outlet(db_session)
    task = _make_task(source, source.outlets[0])
    extraction = StatementExtractionResult(
        statement="W 公司公告：与 Z 集团签署合资协议，Q4 设立合资公司",
        rationale="文章公告段主体陈述",
    )
    collector = Collector(
        llm=make_fake_llm_collect(make_selection_article(), extraction),
        session=db_session,
        model="deepseek-chat",
    )
    first = collector.collect_outlet(
        task=task,
        html=ENTRY_LISTING_HTML,
        fetch_article=_fetch_pages({ARTICLE_URL: ARTICLE_HTML}),
        store=FakeSnapshotStore(),
    )
    assert isinstance(first, IntelligenceItemNewProposal)
    StateMachineExecutor().execute(first, session=db_session)

    media_source = Source(name="行业媒体 A", type=SourceType.MEDIA, confirmed=True)
    db_session.add(media_source)
    db_session.flush()
    media_article_url = "https://media-a.example/repost/jv"
    selection_repost = make_selection_article().model_copy(update={"url": media_article_url})
    media_task = CollectionTask(
        requirement_id=1,
        requirement_name="跟踪",
        outlet_id=source.outlets[0].id,
        source_id=media_source.id,
        source_name="行业媒体 A",
        source_type=SourceType.MEDIA,
        outlet_name=None,
        url="https://media-a.example/repost",
    )
    media_collector = Collector(
        llm=make_fake_llm_collect(selection_repost, extraction),
        session=db_session,
        model="deepseek-chat",
    )

    proposal = media_collector.collect_outlet(
        task=media_task,
        html=ENTRY_LISTING_HTML,
        fetch_article=_fetch_pages({media_article_url: ARTICLE_HTML}),  # 同文不同 URL
        store=FakeSnapshotStore(),
    )

    assert isinstance(proposal, ItemProvenanceAppendProposal)
    assert proposal.payload.source_name == "行业媒体 A"
    assert proposal.payload.original_url == media_article_url
    StateMachineExecutor().execute(proposal, session=db_session)
    nodes = db_session.scalars(select(ProvenanceChainNode)).all()
    assert len(nodes) == 2


def test_collect_llm_no_statement_returns_none(db_session) -> None:
    """抽取判空（单跳）→ 返回 None，选链与抽取计量均已发生。"""
    source = _seed_confirmed_w_outlet(db_session)
    task = _make_task(source, source.outlets[0])
    empty_extraction = StatementExtractionResult(statement="", rationale="页面无情报价值内容")
    collector = Collector(
        llm=make_fake_llm_collect(make_selection_self(), empty_extraction),
        session=db_session,
        model="deepseek-chat",
    )

    proposal = collector.collect_outlet(
        task=task,
        html="<html><body>关于我们</body></html>",
        fetch_article=_fetch_pages({}),
        store=FakeSnapshotStore(),
    )

    assert proposal is None
    calls = db_session.scalars(select(LlmCall)).all()
    assert [c.target for c in calls] == ["outlet_link_select", "outlet_collection"]


def test_collect_without_store_lands_no_snapshot_key(db_session) -> None:
    """store 缺省（试采集预览）：提案照常产出，快照键为空（预览不落账不存对象）。"""
    source = _seed_confirmed_w_outlet(db_session)
    task = _make_task(source, source.outlets[0])
    extraction = StatementExtractionResult(
        statement="W 公司公告：与 Z 集团签署合资协议，Q4 设立合资公司",
        rationale="文章公告段主体陈述",
    )
    collector = Collector(
        llm=make_fake_llm_collect(make_selection_self(), extraction),
        session=db_session,
        model="deepseek-chat",
    )

    proposal = collector.collect_outlet(
        task=task,
        html=ARTICLE_HTML,
        fetch_article=_fetch_pages({}),
        store=None,
    )

    assert isinstance(proposal, IntelligenceItemNewProposal)
    assert proposal.payload.snapshot_object_key is None
