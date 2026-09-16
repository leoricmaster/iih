"""采集智能体 Collector 单测（doc-06 §3）：人工提交归因 + 自动拉取两跳路径。"""

import dataclasses
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from conftest import (
    FakeSnapshotStore,
    make_fake_llm,
    make_fake_llm_collect,
    make_fake_llm_explore,
    make_fake_llm_manual,
    make_fake_tavily,
    make_selection_article,
    make_selection_self,
)
from iih.agents.collector import (
    Collector,
    ExplorationAttributionResult,
    ExplorationKeywordResult,
    ExplorationResultSelectionResult,
    ManualExtractionResult,
    ManualStatement,
    StatementExtractionResult,
)
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
from iih.tools import search as search_module
from iih.tools.html_normalize import fingerprint, normalize
from iih.tools.search import SearchResult

STATEMENT = "W 公司渠道大会：下一代电驱矿卡计划 2027Q2 量产"


def test_manual_submission_builds_lead_proposal_with_metering(db_session, w_attribution) -> None:
    """支撑 IIH-01.01 AC#1：纪要抽取陈述 + 归因补记信源与途径，组装线索提案。"""
    collector = Collector(
        llm=make_fake_llm(w_attribution, prompt_tokens=120, completion_tokens=60),
        session=db_session,
        model="deepseek-chat",
    )

    proposals = collector.submit_manual(medium_code="meeting_discussion", statement=STATEMENT)
    assert len(proposals) == 1
    result = StateMachineExecutor().execute(proposals[0], session=db_session)

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
    assert (
        proposals[0].rationale == "纪要中的客观要点（归因：陈述主体为 W 公司，发布场景为渠道大会）"
    )

    # LLM 调用计量入账：抽取 + 归因各一笔（智能体/对象/token/时间/模型）
    calls = db_session.scalars(select(LlmCall)).all()
    assert len(calls) == 2
    assert all(c.agent == "collector" and c.model == "deepseek-chat" for c in calls)
    assert all(c.prompt_tokens == 120 and c.completion_tokens == 60 for c in calls)


def test_manual_submission_extracts_multiple_statements(db_session, w_attribution) -> None:
    """纪要多条陈述：一次提交 → 每条陈述一个线索，共享归因与快照（doc-07 §2.3）。"""
    minutes = f"{STATEMENT}。\n李总另提到：2027 年研发投入翻倍。"
    extraction = ManualExtractionResult(
        statements=[
            ManualStatement(statement=STATEMENT, rationale="第一条要点"),
            ManualStatement(
                statement="李总提到：2027 年研发投入翻倍",
                event_time=datetime(2027, 1, 1),
                rationale="第二条要点",
            ),
        ]
    )
    collector = Collector(
        llm=make_fake_llm_manual(extraction, w_attribution),
        session=db_session,
        model="deepseek-chat",
    )

    proposals = collector.submit_manual(medium_code="meeting_discussion", statement=minutes)
    assert len(proposals) == 2

    items = []
    for proposal in proposals:
        result = StateMachineExecutor().execute(proposal, session=db_session)
        items.append(db_session.get(IntelligenceItem, result.item_id))

    assert [i.statement for i in items] == [STATEMENT, "李总提到：2027 年研发投入翻倍"]
    assert items[0].event_time is None
    assert items[1].event_time == datetime(2027, 1, 1, tzinfo=UTC)
    assert {i.content_fingerprint for i in items}.__len__() == 2  # 指纹按陈述区分
    assert all(i.original_snapshot == minutes for i in items)  # 快照 = 提交全文
    assert all(i.source.name == "W 公司" and i.outlet.name == "渠道大会现场" for i in items)
    assert len(db_session.scalars(select(Source)).unique().all()) == 1  # 归因一次、信源复用


def test_manual_submission_without_intelligence_skips_attribution(
    db_session, w_attribution
) -> None:
    """抽取为空：不调归因、不产提案（计量只记抽取一笔）。"""
    collector = Collector(
        llm=make_fake_llm_manual(ManualExtractionResult(statements=[]), w_attribution),
        session=db_session,
        model="deepseek-chat",
    )

    assert collector.submit_manual(medium_code="meeting_discussion", statement="寒暄闲聊") == []
    assert len(db_session.scalars(select(LlmCall)).all()) == 1


def test_manual_submission_without_outlet(db_session, w_attribution) -> None:
    attribution = w_attribution.model_copy(update={"outlet_name": None})
    collector = Collector(llm=make_fake_llm(attribution), session=db_session, model="deepseek-chat")

    proposals = collector.submit_manual(medium_code="industry_exchange", statement=STATEMENT)

    assert proposals[0].provenance.outlet_name is None
    result = StateMachineExecutor().execute(proposals[0], session=db_session)
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
        for proposal in collector.submit_manual(
            medium_code="meeting_discussion", statement=statement
        ):
            executor.execute(proposal, session=db_session)

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


# ---- 池外自由探索（IIH-05.02） ----


OUTSIDE_URL = "https://outside.example/news/release"
OUTSIDE_HTML = """
<html><head><title>行业媒体 Z</title></head><body>
  <main><p>行业媒体 Z 报道：某公司 Q3 财报发布。</p></main>
</body></html>
"""


def _make_task_with_explore(
    source: Source,
    outlet: Outlet,
    *,
    explore_ratio: float = 1.0,
    url: str = ENTRY_URL,
    content_spec: str = "主题：W 公司矿卡订单",
) -> CollectionTask:
    task = _make_task(source, outlet, url=url)
    return dataclasses.replace(task, explore_ratio=explore_ratio, content_spec=content_spec)


def _patch_tavily(monkeypatch, results: list[SearchResult]) -> None:
    """注入 Tavily 替身，避免真实 HTTP 调用。"""
    monkeypatch.setattr(search_module, "search", make_fake_tavily(results))


def test_explore_ratio_zero_skips_exploration(db_session, monkeypatch) -> None:
    """IIH-05.02 DoD#2：explore_ratio=0 不触发探索，无探索 LLM 调用。"""
    source = _seed_confirmed_w_outlet(db_session)
    task = _make_task_with_explore(source, source.outlets[0], explore_ratio=0.0)
    extraction = StatementExtractionResult(
        statement="W 公司公告：与 Z 集团签署合资协议，Q4 设立合资公司",
        rationale="文章公告段主体陈述",
    )
    exploration_keywords = ExplorationKeywordResult(
        keywords=["W 公司", "矿卡", "订单"], rationale="提取自内容规格"
    )
    exploration_selection = ExplorationResultSelectionResult(
        url=OUTSIDE_URL, rationale="明确发布主体"
    )
    exploration_attr = ExplorationAttributionResult(
        source_name="行业媒体 Z",
        source_type=SourceType.MEDIA,
        rationale="探索目标主体为行业媒体 Z",
    )
    collector = Collector(
        llm=make_fake_llm_explore(
            make_selection_article(),
            extraction,
            exploration_keywords,
            exploration_selection,
            exploration_attr,
        ),
        session=db_session,
        model="deepseek-chat",
    )
    _patch_tavily(
        monkeypatch,
        [SearchResult(url=OUTSIDE_URL, title="行业媒体 Z：Q3 财报", content="某公司 Q3 财报")],
    )

    proposal = collector.collect_outlet(
        task=task,
        html=ENTRY_LISTING_HTML,
        fetch_article=_fetch_pages({ARTICLE_URL: ARTICLE_HTML, OUTSIDE_URL: OUTSIDE_HTML}),
        store=FakeSnapshotStore(),
    )

    assert isinstance(proposal, IntelligenceItemNewProposal)
    calls = db_session.scalars(select(LlmCall)).all()
    assert [c.target for c in calls] == ["outlet_link_select", "outlet_collection"]
    # 无新信源落账
    assert db_session.scalars(select(Source).where(Source.name == "行业媒体 Z")).first() is None


def test_explore_ratio_one_triggers_source_discovery(db_session, monkeypatch) -> None:
    """IIH-05.02 AC#1：explore_ratio=1 触发池外探索，Tavily 检索 → LLM 选链
    → fetch → 归因 → 信源未登记产出 SourceDiscoveryProposal 落账 confirmed=False。"""
    source = _seed_confirmed_w_outlet(db_session)
    task = _make_task_with_explore(source, source.outlets[0], explore_ratio=1.0)
    extraction = StatementExtractionResult(
        statement="W 公司公告：与 Z 集团签署合资协议，Q4 设立合资公司",
        rationale="文章公告段主体陈述",
    )
    exploration_keywords = ExplorationKeywordResult(
        keywords=["W 公司", "矿卡", "订单"], rationale="提取自内容规格"
    )
    exploration_selection = ExplorationResultSelectionResult(
        url=OUTSIDE_URL, rationale="明确发布主体"
    )
    exploration_attr = ExplorationAttributionResult(
        source_name="行业媒体 Z",
        source_type=SourceType.MEDIA,
        rationale="探索目标主体为行业媒体 Z",
    )
    collector = Collector(
        llm=make_fake_llm_explore(
            make_selection_article(),
            extraction,
            exploration_keywords,
            exploration_selection,
            exploration_attr,
        ),
        session=db_session,
        model="deepseek-chat",
    )
    _patch_tavily(
        monkeypatch,
        [SearchResult(url=OUTSIDE_URL, title="行业媒体 Z：Q3 财报", content="某公司 Q3 财报")],
    )

    proposal = collector.collect_outlet(
        task=task,
        html=ENTRY_LISTING_HTML,
        fetch_article=_fetch_pages({ARTICLE_URL: ARTICLE_HTML, OUTSIDE_URL: OUTSIDE_HTML}),
        store=FakeSnapshotStore(),
    )

    # 主任务照常产出（探索为副产品，不阻断）
    assert isinstance(proposal, IntelligenceItemNewProposal)
    # 探索新信源落账
    discovered = db_session.scalars(select(Source).where(Source.name == "行业媒体 Z")).first()
    assert discovered is not None
    assert discovered.confirmed is False  # 待确认
    assert discovered.type is SourceType.MEDIA
    assert discovered.discovered_entry == OUTSIDE_URL  # 发现来源 URL（确认时建途径）
    # 计量：选链 + 抽取 + 关键词 + 选链 + 归因（5 次 LLM，4 次在探索段）
    calls = db_session.scalars(select(LlmCall)).all()
    assert [c.target for c in calls] == [
        "outlet_link_select",
        "outlet_collection",
        "outlet_exploration",  # 关键词提取
        "outlet_exploration",  # 检索结果选链
        "outlet_exploration",  # 归因
    ]


def test_explore_skips_when_source_already_registered(db_session, monkeypatch) -> None:
    """探索归因命中介于已登记信源名：不重复建，主任务不受影响。"""
    source = _seed_confirmed_w_outlet(db_session)
    db_session.add(Source(name="行业媒体 Z", type=SourceType.MEDIA, confirmed=True, credit="C"))
    db_session.flush()
    task = _make_task_with_explore(source, source.outlets[0], explore_ratio=1.0)
    extraction = StatementExtractionResult(statement="...", rationale="依据")
    exploration_keywords = ExplorationKeywordResult(keywords=["W 公司"], rationale="依据")
    exploration_selection = ExplorationResultSelectionResult(url=OUTSIDE_URL, rationale="依据")
    exploration_attr = ExplorationAttributionResult(
        source_name="行业媒体 Z", source_type=SourceType.MEDIA, rationale="依据"
    )
    collector = Collector(
        llm=make_fake_llm_explore(
            make_selection_article(),
            extraction,
            exploration_keywords,
            exploration_selection,
            exploration_attr,
        ),
        session=db_session,
        model="deepseek-chat",
    )
    _patch_tavily(
        monkeypatch,
        [SearchResult(url=OUTSIDE_URL, title="行业媒体 Z", content="...")],
    )

    proposal = collector.collect_outlet(
        task=task,
        html=ENTRY_LISTING_HTML,
        fetch_article=_fetch_pages({ARTICLE_URL: ARTICLE_HTML, OUTSIDE_URL: OUTSIDE_HTML}),
        store=FakeSnapshotStore(),
    )

    assert isinstance(proposal, IntelligenceItemNewProposal)
    # 不重复建「行业媒体 Z」
    zs = db_session.scalars(select(Source).where(Source.name == "行业媒体 Z")).all()
    assert len(zs) == 1
    assert zs[0].confirmed is True  # 仍是已确认原行


def test_explore_skips_when_attribution_empty(db_session, monkeypatch) -> None:
    """探索目标无明确主体信息：归因返回空 source_name，不产出提案。"""
    source = _seed_confirmed_w_outlet(db_session)
    task = _make_task_with_explore(source, source.outlets[0], explore_ratio=1.0)
    extraction = StatementExtractionResult(statement="...", rationale="依据")
    exploration_keywords = ExplorationKeywordResult(keywords=["W 公司"], rationale="依据")
    exploration_selection = ExplorationResultSelectionResult(url=OUTSIDE_URL, rationale="依据")
    exploration_attr = ExplorationAttributionResult(
        source_name="", source_type=SourceType.OTHER, rationale="无明确主体"
    )
    collector = Collector(
        llm=make_fake_llm_explore(
            make_selection_article(),
            extraction,
            exploration_keywords,
            exploration_selection,
            exploration_attr,
        ),
        session=db_session,
        model="deepseek-chat",
    )
    _patch_tavily(
        monkeypatch,
        [SearchResult(url=OUTSIDE_URL, title="...", content="...")],
    )

    collector.collect_outlet(
        task=task,
        html=ENTRY_LISTING_HTML,
        fetch_article=_fetch_pages({ARTICLE_URL: ARTICLE_HTML, OUTSIDE_URL: OUTSIDE_HTML}),
        store=FakeSnapshotStore(),
    )

    assert db_session.scalars(select(Source).where(Source.name == "")).first() is None


def test_explore_search_failure_does_not_block_main(db_session, monkeypatch) -> None:
    """Tavily 检索失败：静默跳过，主任务照常产出。"""
    source = _seed_confirmed_w_outlet(db_session)
    task = _make_task_with_explore(source, source.outlets[0], explore_ratio=1.0)
    extraction = StatementExtractionResult(statement="...", rationale="依据")
    exploration_keywords = ExplorationKeywordResult(keywords=["W 公司"], rationale="依据")
    exploration_selection = ExplorationResultSelectionResult(url=OUTSIDE_URL, rationale="依据")
    exploration_attr = ExplorationAttributionResult(
        source_name="行业媒体 Z", source_type=SourceType.MEDIA, rationale="依据"
    )
    collector = Collector(
        llm=make_fake_llm_explore(
            make_selection_article(),
            extraction,
            exploration_keywords,
            exploration_selection,
            exploration_attr,
        ),
        session=db_session,
        model="deepseek-chat",
    )

    def _failing_search(*args, **kwargs):
        from iih.tools.search import SearchError

        raise SearchError("Tavily 不可用")

    monkeypatch.setattr(search_module, "search", _failing_search)

    proposal = collector.collect_outlet(
        task=task,
        html=ENTRY_LISTING_HTML,
        fetch_article=_fetch_pages({ARTICLE_URL: ARTICLE_HTML}),
        store=FakeSnapshotStore(),
    )

    assert isinstance(proposal, IntelligenceItemNewProposal)  # 主任务不受影响
    assert (
        db_session.scalars(select(Source).where(Source.name == "行业媒体 Z")).first() is None
    )  # 探索失败未建信源


def test_explore_skips_when_content_spec_blank(db_session, monkeypatch) -> None:
    """IR.content_spec 为空：探索环节静默跳过（无关键词来源）。"""
    source = _seed_confirmed_w_outlet(db_session)
    task = _make_task_with_explore(source, source.outlets[0], explore_ratio=1.0, content_spec="")
    extraction = StatementExtractionResult(statement="...", rationale="依据")
    exploration_keywords = ExplorationKeywordResult(keywords=[], rationale="空")
    exploration_selection = ExplorationResultSelectionResult(url="", rationale="空")
    exploration_attr = ExplorationAttributionResult(
        source_name="", source_type=SourceType.OTHER, rationale="空"
    )
    collector = Collector(
        llm=make_fake_llm_explore(
            make_selection_article(),
            extraction,
            exploration_keywords,
            exploration_selection,
            exploration_attr,
        ),
        session=db_session,
        model="deepseek-chat",
    )
    _patch_tavily(monkeypatch, [])

    collector.collect_outlet(
        task=task,
        html=ENTRY_LISTING_HTML,
        fetch_article=_fetch_pages({ARTICLE_URL: ARTICLE_HTML}),
        store=FakeSnapshotStore(),
    )

    # content_spec 空 → 不调关键词 LLM，不落新信源
    calls = db_session.scalars(select(LlmCall)).all()
    assert all(c.target != "outlet_exploration" for c in calls)
    assert db_session.scalars(select(Source).where(Source.name == "")).first() is None
