"""Web 页单测（doc-07 §3、§5、原型）：录入素材、信源库、收件箱、条目详情与反馈。"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from conftest import (
    FakeSnapshotStore,
    make_fake_llm,
    make_fake_llm_dispatch,
    make_fake_llm_manual,
    make_fake_llm_review,
    make_manual_extraction,
    make_selection_article,
    make_selection_self,
)
from iih.agents.collector import ManualExtractionResult, StatementExtractionResult
from iih.agents.reviewer import ReviewJudgmentResult
from iih.ledger.credit import SOURCE_CREDIT_FORMULA_VERSION
from iih.ledger.formula import CONTENT_CREDIBILITY_FORMULA_VERSION
from iih.ledger.models import (
    CreditAdjustment,
    Feedback,
    FeedbackType,
    IntelligenceItem,
    IntelligenceRequirement,
    IntelligenceRequirementStatus,
    ItemMode,
    ItemStatus,
    LlmCall,
    Medium,
    Modality,
    Outlet,
    ProvenanceChainNode,
    RejectionReasonEnum,
    ReviewDecision,
    ReviewDecisionEnum,
    Source,
    SourceAlias,
    SourceType,
    VerificationOutcome,
    VerificationRecord,
)
from iih.tools.fetcher import FetcherError
from iih.web.app import create_app
from iih.web.deps import get_session

STATEMENT = "W 公司渠道大会：下一代电驱矿卡计划 2027Q2 量产"


@pytest.fixture
def client(db_session, fake_llm) -> TestClient:
    app = create_app()
    app.state.llm = fake_llm
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client


def test_submissions_page_lists_offline_mediums(client: TestClient) -> None:
    response = client.get("/submissions")

    assert response.status_code == 200
    assert "录入素材" in response.text
    for option in ("会议讨论", "行业展会", "用户访谈", "行业交流", "文档阅读"):
        assert option in response.text
    assert '<option value="internet"' not in response.text  # 互联网为自动拉取，不走本页


def test_submit_lands_lead_end_to_end(client: TestClient, db_session) -> None:
    """对应 IIH-01.01 AC#1：提交落账「线索」，溯源五要素齐备、归因补记（端到端）。"""
    response = client.post(
        "/submissions",
        data={"medium_code": "meeting_discussion", "statement": STATEMENT},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert STATEMENT in response.text  # 近期人工提交列表可见
    assert "已提交：抽取陈述 1 条，进入流水线" in response.text  # 成功 toast
    items = db_session.scalars(select(IntelligenceItem)).all()
    assert len(items) == 1
    assert items[0].status is ItemStatus.LEAD
    assert items[0].source is not None and items[0].source.name == "W 公司"


def test_submit_extracts_multiple_statements(db_session, w_attribution) -> None:
    """纪要多条陈述：一次提交落账多条线索，toast 回显条数（doc-07 §2.3）。"""
    other = "李总提到：2027 年研发投入翻倍"
    app = create_app()
    app.state.llm = make_fake_llm_manual(make_manual_extraction(STATEMENT, other), w_attribution)
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as multi_client:
        response = multi_client.post(
            "/submissions",
            data={"medium_code": "meeting_discussion", "statement": f"{STATEMENT}。\n{other}。"},
            follow_redirects=True,
        )

    assert response.status_code == 200
    assert "已提交：抽取陈述 2 条，进入流水线" in response.text
    items = db_session.scalars(select(IntelligenceItem)).all()
    assert len(items) == 2
    assert {i.statement for i in items} == {STATEMENT, other}
    assert all(i.status is ItemStatus.LEAD for i in items)


def test_submit_without_intelligence_reports_error(db_session, w_attribution) -> None:
    """抽取为空：回显错误、不落账。"""
    app = create_app()
    app.state.llm = make_fake_llm_manual(ManualExtractionResult(statements=[]), w_attribution)
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as empty_client:
        response = empty_client.post(
            "/submissions", data={"medium_code": "meeting_discussion", "statement": "寒暄闲聊"}
        )

    assert '<div class="flash err">未能从提交文本中识别出情报陈述</div>' in response.text
    assert ">寒暄闲聊</textarea>" in response.text  # 拦截时已填内容保留
    assert 'value="meeting_discussion" selected' in response.text
    assert db_session.scalars(select(IntelligenceItem)).first() is None


def test_submit_with_missing_fields_is_blocked(client: TestClient, db_session) -> None:
    """对应 IIH-01.01 AC#2：必填缺失表单拦截，不生成提案。"""
    response = client.post("/submissions", data={"medium_code": "", "statement": ""})

    assert response.status_code == 200  # 重渲染表单并提示
    assert "请选择媒介" in response.text
    assert "请上传附件，或填写文字纪要" in response.text
    assert db_session.scalars(select(IntelligenceItem)).first() is None  # 不生成提案


def test_submit_with_internet_medium_is_blocked(client: TestClient, db_session) -> None:
    response = client.post("/submissions", data={"medium_code": "internet", "statement": STATEMENT})

    assert "互联网媒介为自动拉取" in response.text
    assert db_session.scalars(select(IntelligenceItem)).first() is None


def test_submit_shows_rejection_reasons(client: TestClient, db_session, w_attribution) -> None:
    # 归因产出空信源名 → 提案被状态机驳回，原因回显表单页
    app = create_app()
    empty_attribution = w_attribution.model_copy(update={"source_name": ""})
    app.state.llm = make_fake_llm(empty_attribution)
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as blocked_client:
        response = blocked_client.post(
            "/submissions", data={"medium_code": "meeting_discussion", "statement": STATEMENT}
        )

    assert "溯源缺失：信源归因" in response.text


# ---- IIH-01.07 信源库页 ----


@pytest.fixture
def sources_client(db_session) -> TestClient:
    """信源库页客户端：不需要 LLM（登记不经智能体）。"""
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client


def test_sources_page_lists_confirmed_sources(sources_client: TestClient) -> None:
    response = sources_client.get("/sources")

    assert response.status_code == 200
    assert "信源库" in response.text
    assert "登记信源" in response.text
    for label in ("公司", "政府", "组织", "媒体", "人物", "其他"):
        assert label in response.text  # 类型下拉 6 项
    assert "信用档 A–F" in response.text  # 初始档 tooltip（doc-04 §2.3）


def test_register_lands_source_and_outlet_end_to_end(
    sources_client: TestClient, db_session
) -> None:
    """对应 IIH-01.07 AC#1：登记主体「W 公司」+ 首条途径（官网 · 互联网）→ 列表两栏可见。"""
    response = sources_client.post(
        "/sources",
        data={
            "source_name": "W 公司",
            "source_type": "company",
            "outlet_name": "官网",
            "outlet_entry": "https://w-mining.example/news",
            "initial_credit": "B",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "W 公司" in response.text  # 列表主体栏可见
    assert "官网" in response.text  # 列表途径栏可见

    sources = db_session.scalars(select(Source).where(Source.name == "W 公司")).unique().all()
    assert len(sources) == 1
    assert sources[0].confirmed is True
    assert sources[0].type is SourceType.COMPANY
    assert sources[0].credit == "B"  # 初始档必填（doc-04 §2.3）
    outlets = (
        db_session.scalars(select(Outlet).where(Outlet.source_id == sources[0].id)).unique().all()
    )
    assert len(outlets) == 1
    assert outlets[0].name == "官网"
    assert outlets[0].entry == "https://w-mining.example/news"
    assert outlets[0].medium.code == "internet"


def test_register_with_initial_credit_sets_grade(sources_client: TestClient, db_session) -> None:
    """登记时人工设初始信用档（冷启动设档）：落账 credit，画像档位可见。"""
    response = sources_client.post(
        "/sources",
        data={
            "source_name": "W 公司",
            "source_type": "company",
            "outlet_name": "官网",
            "outlet_entry": "https://w-mining.example/news",
            "initial_credit": "B",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert '<span class="pill rating">B</span>' in response.text
    source = db_session.scalars(select(Source).where(Source.name == "W 公司")).unique().one()
    assert source.credit == "B"

    blocked = sources_client.post(
        "/sources",
        data={
            "source_name": "Z 集团",
            "source_type": "company",
            "outlet_name": "官网",
            "outlet_entry": "https://z.example/news",
            "initial_credit": "X",
        },
    )
    assert "初始信用档需为 A–F" in blocked.text
    assert db_session.scalars(select(Source).where(Source.name == "Z 集团")).first() is None


def test_register_with_missing_fields_is_blocked(sources_client: TestClient, db_session) -> None:
    """对应 IIH-01.07 AC#2：必填字段缺失 → 表单拦截、不落账。"""
    response = sources_client.post(
        "/sources",
        data={
            "source_name": "",
            "source_type": "",
            "outlet_name": "",
            "outlet_entry": "",
        },
    )

    assert response.status_code == 200  # 重渲染表单并提示
    assert "请填写主体名称" in response.text
    assert "请选择类型" in response.text
    assert "请填写途径名" in response.text
    assert "请填写采集入口" in response.text
    assert "请选择初始信用档" in response.text  # 初始档必填（doc-04 §2.3）
    assert db_session.scalars(select(Source)).first() is None  # 不落账


def test_register_shows_rejection_reasons(sources_client: TestClient, db_session) -> None:
    """状态机驳回（信源名重复）→ 原因回显表单页。"""
    sources_client.post(
        "/sources",
        data={
            "source_name": "W 公司",
            "source_type": "company",
            "outlet_name": "官网",
            "outlet_entry": "https://w-mining.example/news",
            "initial_credit": "B",
        },
    )
    response = sources_client.post(
        "/sources",
        data={
            "source_name": "W 公司",
            "source_type": "company",
            "outlet_name": "公众号",
            "outlet_entry": "公众号 ID：w-official",
            "initial_credit": "B",
        },
    )

    assert "信源名已存在" in response.text
    sources = db_session.scalars(select(Source).where(Source.name == "W 公司")).unique().all()
    assert len(sources) == 1  # 第二次登记被驳回，未新增


# ---- IIH-01.04 收件箱与条目详情 ----


@pytest.fixture
def inbox_client(db_session) -> TestClient:
    """收件箱客户端：浏览页不需要 LLM。"""
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client


def _seed_verified_item(
    db_session,
    *,
    statement: str = "W 公司公告：与 Z 集团签署合资协议",
    source_name: str = "W 公司",
):
    """预置一条已核实条目：转引链单节点 + 核实记录（B2），溯源五要素齐备。"""
    medium = db_session.scalars(select(Medium).where(Medium.code == "internet")).one()
    modality = db_session.scalars(select(Modality).where(Modality.code == "webpage")).one()
    source = Source(name=source_name, type=SourceType.COMPANY, confirmed=True, credit="B")
    outlet = Outlet(source=source, name="官网", entry="https://w-mining.example/news")
    item = IntelligenceItem(
        statement=statement,
        status=ItemStatus.VERIFIED,
        rating="B2",
        mode=ItemMode.AUTOMATED,
        medium=medium,
        modality=modality,
        collected_at=datetime(2026, 9, 14, 10, 0, tzinfo=UTC),
        original_snapshot="W 公司今日公告，与 Z 集团签署合资协议。",
        source=source,
        outlet=outlet,
    )
    db_session.add_all([source, outlet, item])
    db_session.flush()
    db_session.add(
        ProvenanceChainNode(
            item=item,
            source=source,
            modality=modality,
            medium=medium,
            collected_at=datetime(2026, 9, 14, 10, 0, tzinfo=UTC),
        )
    )
    rationale = "穿透转引链得独立信源 N=1，出处信源可靠度 R=B，公式出内容可信度 2，组装评级 B2"
    db_session.add(
        VerificationRecord(
            item=item,
            outcome=VerificationOutcome.VERIFIED,
            independent_source_count=1,
            source_reliability="B",
            content_credibility=2,
            rating="B2",
            formula_version=CONTENT_CREDIBILITY_FORMULA_VERSION,
            rationale=rationale,
        )
    )
    db_session.flush()
    return item


def test_inbox_is_homepage_and_lists_verified_items(inbox_client: TestClient, db_session) -> None:
    """对应 IIH-01.04 AC#1：收件箱为首页，列表展示陈述摘要 + 二维评级 + 状态。"""
    item = _seed_verified_item(db_session)

    response = inbox_client.get("/")

    assert response.status_code == 200
    assert "收件箱" in response.text
    assert "W 公司公告：与 Z 集团签署合资协议" in response.text  # 陈述摘要
    assert "B2" in response.text  # 二维评级
    assert "已核实" in response.text  # 状态
    assert f'href="/items/{item.id}"' in response.text  # 条目链接进详情


def test_inbox_hides_unverified_items(inbox_client: TestClient, db_session) -> None:
    """收件箱只收已核实条目：线索/候选不出现；空态有提示。"""
    medium = db_session.scalars(select(Medium).where(Medium.code == "internet")).one()
    modality = db_session.scalars(select(Modality).where(Modality.code == "webpage")).one()
    db_session.add(
        IntelligenceItem(
            statement="未经核实的线索",
            status=ItemStatus.LEAD,
            mode=ItemMode.MANUAL,
            medium=medium,
            modality=modality,
            collected_at=datetime(2026, 9, 14, 9, 0, tzinfo=UTC),
            original_snapshot="草稿",
        )
    )

    response = inbox_client.get("/")

    assert response.status_code == 200
    assert "未经核实的线索" not in response.text
    assert "无待反馈条目" in response.text


def test_inbox_drops_item_after_feedback_lands(inbox_client: TestClient, db_session) -> None:
    """反馈落账即出队：提交「有效」后条目从收件箱消失（状态仍为已核实，靠反馈记录判定）。

    主列表与侧栏徽标同口径：徽标归零后不渲染（避免蓝底 0 噪音）。
    """
    item = _seed_verified_item(db_session)

    before = inbox_client.get("/")
    assert '<span class="cnt">1</span>' in before.text

    inbox_client.post(f"/items/{item.id}/feedback", data={"feedback_type": "valid"})

    response = inbox_client.get("/")
    assert response.status_code == 200
    assert "W 公司公告：与 Z 集团签署合资协议" not in response.text
    assert "无待反馈条目" in response.text
    assert '<span class="cnt">' not in response.text  # 0 不渲染徽标


def test_item_detail_shows_provenance_and_rating_basis(
    inbox_client: TestClient, db_session
) -> None:
    """对应 IIH-01.04 AC#2：详情可看溯源五要素与评级依据。"""
    item = _seed_verified_item(db_session)

    response = inbox_client.get(f"/items/{item.id}")

    assert response.status_code == 200
    # 溯源五要素（元数据折叠区）：载体 / 媒介 / 采集时间 / 原文快照 / 信源与途径归因
    assert "元数据" in response.text
    assert "互联网 / 网页" in response.text  # 媒介 / 载体
    assert "2026-09-14 18:00" in response.text  # 采集时间（UTC 10:00 → 展示时区）
    assert "W 公司今日公告，与 Z 集团签署合资协议。" in response.text  # 原文快照
    assert "官网" in response.text  # 途径归因（元数据 + 转引链）
    assert ">转引链" in response.text
    # 评级依据：核实记录 + N/R/内容可信度/公式版本
    assert "评级依据" in response.text
    assert "穿透转引链得独立信源 N=1" in response.text
    assert "content_credibility_v1" in response.text
    assert "（当前）" in response.text  # 评级历史首行版本标记


def test_item_detail_returns_404_for_unknown_item(inbox_client: TestClient) -> None:
    response = inbox_client.get("/items/9999")

    assert response.status_code == 404


# ---- IIH-01.05 一键类型化反馈 ----


def test_quick_feedback_from_inbox_card_lands_with_default_reason(
    inbox_client: TestClient, db_session
) -> None:
    """对应 IIH-01.05 AC#1：收件箱卡片一键「有效」→ 落账、默认理由「快捷 · 有效」、回来源页。"""
    item = _seed_verified_item(db_session)

    response = inbox_client.post(
        f"/items/{item.id}/feedback",
        data={"feedback_type": "valid"},
        headers={"referer": "http://testserver/"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    from urllib.parse import parse_qs, urlsplit

    loc = response.headers["location"]
    assert loc.startswith("http://testserver/?flash=")  # 回来源页且带提示
    assert parse_qs(urlsplit(loc).query)["flash"] == ["已记录反馈：有效"]
    feedback = db_session.scalars(select(Feedback)).unique().one()
    assert feedback.item_id == item.id
    assert feedback.feedback_type is FeedbackType.VALID
    assert feedback.reason == "快捷 · 有效"


def test_factual_error_without_reason_blocked_on_detail(
    inbox_client: TestClient, db_session
) -> None:
    """对应 IIH-01.05 AC#2：详情页选「事实错误」未填理由 → 校验拦截不落账；补理由后可提交。"""
    item = _seed_verified_item(db_session)

    blocked = inbox_client.post(
        f"/items/{item.id}/feedback", data={"feedback_type": "factual_error", "reason": " "}
    )

    assert "事实错误反馈必须填写理由" in blocked.text
    assert db_session.scalars(select(Feedback)).unique().first() is None

    submitted = inbox_client.post(
        f"/items/{item.id}/feedback",
        data={"feedback_type": "factual_error", "reason": "合资协议从未签署"},
        follow_redirects=False,
    )

    assert submitted.status_code == 303
    feedback = db_session.scalars(select(Feedback)).unique().one()
    assert feedback.feedback_type is FeedbackType.FACTUAL_ERROR
    assert feedback.reason == "合资协议从未签署"


def test_feedback_with_unknown_type_rejected(inbox_client: TestClient, db_session) -> None:
    item = _seed_verified_item(db_session)

    response = inbox_client.post(
        f"/items/{item.id}/feedback", data={"feedback_type": "great", "reason": "x"}
    )

    assert "未知反馈类型：great" in response.text
    assert db_session.scalars(select(Feedback)).unique().first() is None


def test_feedback_to_unknown_item_returns_404(inbox_client: TestClient) -> None:
    response = inbox_client.post(
        "/items/9999/feedback", data={"feedback_type": "valid"}, follow_redirects=False
    )

    assert response.status_code == 404


def test_item_detail_shows_feedback_form_and_records(inbox_client: TestClient, db_session) -> None:
    """详情页反馈表单六类型可选；反馈记录内联在详情（doc-07 §3）。"""
    item = _seed_verified_item(db_session)
    db_session.add(Feedback(item=item, feedback_type=FeedbackType.VALID, reason="快捷 · 有效"))
    db_session.flush()

    response = inbox_client.get(f"/items/{item.id}")

    assert response.status_code == 200
    assert "反馈" in response.text
    for option in (
        "valid",
        "factual_error",
        "duplicate_noise",
        "irrelevant",
        "outdated",
        "rating_dispute",
    ):
        assert f'value="{option}"' in response.text
    assert "反馈记录" in response.text
    assert "快捷 · 有效" in response.text


def test_inbox_offers_one_click_feedback_entry(inbox_client: TestClient, db_session) -> None:
    """收件箱卡片一键反馈：五类型直发 + 事实错误跳详情补理由（doc-07 §5）。"""
    item = _seed_verified_item(db_session)

    response = inbox_client.get("/")

    assert response.status_code == 200
    assert f'action="/items/{item.id}/feedback"' in response.text
    for button_type in ("valid", "duplicate_noise", "irrelevant", "outdated", "rating_dispute"):
        assert f'name="feedback_type" value="{button_type}"' in response.text
    # 事实错误跳详情补理由（fb_type 预选）
    assert f'href="/items/{item.id}?fb_type=factual_error#feedback"' in response.text


# ---- IIH-01.13 壳与原型还原 ----


def test_shell_renders_nav_groups_and_static_css(inbox_client: TestClient, db_session) -> None:
    """对应 IIH-01.13 AC#2：三组导航 + 录入素材全局按钮；探究组置灰标未开通。"""
    _seed_verified_item(db_session)

    response = inbox_client.get("/")
    css = inbox_client.get("/static/app.css")

    assert response.status_code == 200
    assert "＋ 录入素材" in response.text  # 全局动作，不占导航位（doc-07 §3）
    for nav in ("收件箱", "情报条目", "研究课题", "命题", "图谱", "情报需求", "信源库"):
        assert nav in response.text
    assert "未开通" in response.text  # 探究组置灰
    assert '<span class="cnt">1</span>' in response.text  # 收件箱徽标计数
    assert css.status_code == 200
    assert "#sidebar" in css.text


# ---- IIH-01.13 情报条目列表：筛选与检索 ----


def _seed_lead_item(
    db_session, *, statement: str = "未经核实的线索", mode: ItemMode = ItemMode.MANUAL
) -> IntelligenceItem:
    medium = db_session.scalars(select(Medium).where(Medium.code == "internet")).one()
    modality = db_session.scalars(select(Modality).where(Modality.code == "webpage")).one()
    item = IntelligenceItem(
        statement=statement,
        status=ItemStatus.LEAD,
        mode=mode,
        medium=medium,
        modality=modality,
        collected_at=datetime(2026, 9, 14, 9, 0, tzinfo=UTC),
        original_snapshot="草稿",
    )
    db_session.add(item)
    db_session.flush()
    return item


def test_items_page_default_hides_leads(inbox_client: TestClient, db_session) -> None:
    """默认「已核实起」：线索不入默认视图（doc-07 §3）。"""
    _seed_verified_item(db_session)
    _seed_lead_item(db_session)

    response = inbox_client.get("/items")

    assert response.status_code == 200
    assert "W 公司公告：与 Z 集团签署合资协议" in response.text
    assert "未经核实的线索" not in response.text


def test_items_page_status_and_mode_filters(inbox_client: TestClient, db_session) -> None:
    _seed_verified_item(db_session)  # 已核实 · 自动拉取
    _seed_lead_item(db_session)  # 线索 · 人工提交

    leads = inbox_client.get("/items", params={"status": "lead"})
    assert "未经核实的线索" in leads.text
    assert "W 公司公告" not in leads.text

    empty = inbox_client.get("/items", params={"status": "lead", "mode": "automated"})
    assert "当前筛选下无条目" in empty.text

    manual = inbox_client.get("/items", params={"status": "all", "mode": "manual"})
    assert "未经核实的线索" in manual.text
    assert "W 公司公告" not in manual.text


def test_items_page_search_by_statement_and_source(inbox_client: TestClient, db_session) -> None:
    _seed_verified_item(db_session, statement="电驱矿卡量产计划公告", source_name="W 公司")
    _seed_verified_item(db_session, statement="新建电池工厂", source_name="Z 集团")

    by_statement = inbox_client.get("/items", params={"q": "矿卡"})
    assert "电驱矿卡量产计划公告" in by_statement.text
    assert "新建电池工厂" not in by_statement.text

    by_source = inbox_client.get("/items", params={"q": "Z 集团"})
    assert "新建电池工厂" in by_source.text
    assert "电驱矿卡量产计划公告" not in by_source.text


# ---- IIH-01.13 条目详情：状态自适应主区与核查深区 ----


def test_item_detail_lead_shows_pipeline_progress(inbox_client: TestClient, db_session) -> None:
    """线索态主区显示流水线进度（审查/核实待运行）与「立即运行一轮」入口。"""
    item = _seed_lead_item(db_session)

    response = inbox_client.get(f"/items/{item.id}")

    assert response.status_code == 200
    assert "流水线进度" in response.text
    assert "（待运行）" in response.text
    assert 'action="/pipeline/run"' in response.text
    assert 'form="run-one"' in response.text
    assert "评级依据" not in response.text  # 未核实不展示


def test_item_detail_retracted_shows_cascade_box(inbox_client: TestClient, db_session) -> None:
    """作废态展示作废原因与级联影响（事实错误反馈理由）。"""
    item = _seed_verified_item(db_session)
    item.retracted = True
    db_session.add(
        Feedback(item=item, feedback_type=FeedbackType.FACTUAL_ERROR, reason="合资协议从未签署")
    )
    db_session.flush()

    response = inbox_client.get(f"/items/{item.id}")

    assert "作废原因" in response.text
    assert "合资协议从未签署" in response.text
    assert "作废（事实错误）" in response.text  # 状态迁移轨迹


def test_item_detail_chain_marks_attribution_object(inbox_client: TestClient, db_session) -> None:
    """对应 IIH-01.13 AC#3：转引链穿透视图标注信用归因对象（最早引入方 · decision-04）。"""
    medium = db_session.scalars(select(Medium).where(Medium.code == "internet")).one()
    modality = db_session.scalars(select(Modality).where(Modality.code == "webpage")).one()
    media = Source(name="行业媒体 A", type=SourceType.MEDIA, confirmed=True, credit="C")
    origin = Source(name="W 公司", type=SourceType.COMPANY, confirmed=True, credit="B")
    outlet = Outlet(source=origin, name="官网", entry="https://w-mining.example/news")
    item = IntelligenceItem(
        statement="W 公司公告：与 Z 集团签署合资协议",
        status=ItemStatus.VERIFIED,
        rating="B2",
        mode=ItemMode.AUTOMATED,
        medium=medium,
        modality=modality,
        collected_at=datetime(2026, 9, 14, 10, 0, tzinfo=UTC),
        original_snapshot="正文",
        source=origin,
        outlet=outlet,
    )
    db_session.add_all([media, origin, outlet, item])
    db_session.flush()
    db_session.add_all(
        [
            ProvenanceChainNode(  # 媒体最早引入 → 信用归因对象
                item=item,
                source=media,
                modality=modality,
                medium=medium,
                collected_at=datetime(2026, 9, 14, 9, 0, tzinfo=UTC),
            ),
            ProvenanceChainNode(
                item=item,
                source=origin,
                modality=modality,
                medium=medium,
                collected_at=datetime(2026, 9, 14, 10, 0, tzinfo=UTC),
            ),
        ]
    )
    db_session.flush()

    response = inbox_client.get(f"/items/{item.id}")

    assert response.status_code == 200
    assert ">转引链" in response.text
    assert "2 节点" in response.text
    assert "信用归因对象" in response.text
    assert response.text.count("信用归因对象") == 1  # 仅最早引入方
    assert f'href="/sources/{media.id}"' in response.text  # 链节点进信源画像


def test_item_detail_rating_history_lists_versions(inbox_client: TestClient, db_session) -> None:
    """评级历史（版本化 · 可重放）：首行标（当前），历史版本并列。"""
    item = _seed_verified_item(db_session)
    db_session.add(
        VerificationRecord(
            item=item,
            outcome=VerificationOutcome.VERIFIED,
            independent_source_count=1,
            source_reliability="B",
            content_credibility=1,
            rating="B1",
            formula_version=CONTENT_CREDIBILITY_FORMULA_VERSION,
            rationale="首评：仅出处信源单节点",
        )
    )
    db_session.flush()

    response = inbox_client.get(f"/items/{item.id}")

    assert "评级历史" in response.text
    assert "B1" in response.text  # 历史版本
    assert "B2" in response.text
    assert response.text.count("（当前）") == 1  # 首行标记


# ---- IIH-01.13 情报需求全生命周期（浏览器路径） ----


def _create_ir_via_form(
    inbox_client: TestClient, name: str = "跟踪 W 公司", spec: str = "主题：矿卡、订单、战略"
) -> int:
    response = inbox_client.post(
        "/requirements", data={"name": name, "content_spec": spec}, follow_redirects=False
    )
    assert response.status_code == 303
    return int(response.headers["location"].rsplit("/", 1)[-1])


def test_requirement_create_lands_draft(inbox_client: TestClient, db_session) -> None:
    """对应 IIH-01.13 AC#4：新建落草稿，详情页提供确认激活。"""
    ir_id = _create_ir_via_form(inbox_client)

    ir = db_session.get(IntelligenceRequirement, ir_id)
    assert ir is not None
    assert ir.status is IntelligenceRequirementStatus.DRAFT
    detail = inbox_client.get(f"/requirements/{ir_id}")
    assert "草稿" in detail.text
    assert 'value="activate"' in detail.text


def test_requirement_missing_fields_blocked(inbox_client: TestClient, db_session) -> None:
    response = inbox_client.post("/requirements", data={"name": "", "content_spec": ""})

    assert "请填写需求名称" in response.text
    assert "请填写内容规格" in response.text
    assert db_session.scalars(select(IntelligenceRequirement)).first() is None


def test_requirement_full_lifecycle_via_browser(inbox_client: TestClient, db_session) -> None:
    """草稿 → 激活 ⇄ 暂停 → 关闭 → 重开，迁移经提案落账（doc-02 §4.1）。"""
    ir_id = _create_ir_via_form(inbox_client)

    def status() -> IntelligenceRequirementStatus:
        ir = db_session.get(IntelligenceRequirement, ir_id)
        assert ir is not None
        return ir.status

    def act(action: str):
        return inbox_client.post(
            f"/requirements/{ir_id}/action", data={"action": action}, follow_redirects=True
        )

    activated = act("activate")
    assert status() is IntelligenceRequirementStatus.ACTIVE
    assert 'value="pause"' in activated.text  # 激活态提供暂停/关闭

    paused = act("pause")
    assert status() is IntelligenceRequirementStatus.PAUSED
    assert 'value="resume"' in paused.text  # 暂停态提供恢复/关闭

    act("resume")
    assert status() is IntelligenceRequirementStatus.ACTIVE

    closed = act("close")
    assert status() is IntelligenceRequirementStatus.CLOSED
    assert 'value="activate"' in closed.text  # 关闭态可重开

    reopened = act("activate")  # 关闭 → 重开 → 激活
    assert status() is IntelligenceRequirementStatus.ACTIVE
    assert 'value="pause"' in reopened.text  # 回到激活态


def test_requirement_spec_update_while_active(inbox_client: TestClient, db_session) -> None:
    """激活态可微调内容规格，生效于下轮采集（doc-07 §2.2）；空规格拦截。"""
    ir_id = _create_ir_via_form(inbox_client)
    inbox_client.post(f"/requirements/{ir_id}/action", data={"action": "activate"})

    updated = inbox_client.post(
        f"/requirements/{ir_id}/spec",
        data={"content_spec": "主题：矿卡、电池"},
        follow_redirects=True,
    )
    assert 'name="content_spec"' in updated.text  # 激活态保持可编辑
    ir = db_session.get(IntelligenceRequirement, ir_id)
    assert ir is not None and ir.content_spec == "主题：矿卡、电池"

    blocked = inbox_client.post(f"/requirements/{ir_id}/spec", data={"content_spec": " "})
    assert "内容规格不能为空" in blocked.text


def test_requirement_unknown_action_shows_error(inbox_client: TestClient, db_session) -> None:
    ir_id = _create_ir_via_form(inbox_client)

    response = inbox_client.post(
        f"/requirements/{ir_id}/action", data={"action": "hoge"}, follow_redirects=True
    )

    assert "未知动作：hoge" in response.text


def test_requirement_detail_lists_hit_items(inbox_client: TestClient, db_session) -> None:
    """命中条目：审查通过记录匹配本需求的条目（doc-06 §4）；列表以命中计数近似覆盖度量。"""
    ir = IntelligenceRequirement(
        name="跟踪 W 公司", content_spec="主题", status=IntelligenceRequirementStatus.ACTIVE
    )
    item = _seed_verified_item(db_session)
    db_session.add(ir)
    db_session.flush()
    db_session.add(
        ReviewDecision(
            item=item,
            decision=ReviewDecisionEnum.PASS,
            matched_requirement_id=ir.id,
            rationale="陈述主题命中激活需求",
        )
    )
    db_session.flush()

    detail = inbox_client.get(f"/requirements/{ir.id}")
    listing = inbox_client.get("/requirements")

    assert "W 公司公告：与 Z 集团签署合资协议" in detail.text
    assert '<td class="muted">1</td>' in listing.text  # 命中计数


def test_requirement_detail_404_for_unknown(inbox_client: TestClient) -> None:
    assert inbox_client.get("/requirements/9999").status_code == 404


def test_requirement_detail_shows_collect_overview(inbox_client: TestClient, db_session) -> None:
    """采集概览：节奏 + 覆盖途径（Director 同口径）；MVP 透明度补丁（IIH-01.13 第六轮）。"""
    ir_id = _seed_probe_target(db_session)
    detail = inbox_client.get(f"/requirements/{ir_id}")
    assert "采集概览" in detail.text
    assert "W 公司" in detail.text
    assert "官网" in detail.text
    assert "覆盖全部信源" in detail.text


# ---- IIH-03.01 需求级采集配置 ----


def test_requirement_list_shows_config_columns(inbox_client: TestClient, db_session) -> None:
    """列表页展示四项配置列：频率/事件时效/信源/生效窗口。"""
    from datetime import date

    source = Source(name="W 公司", type=SourceType.COMPANY, confirmed=True, credit="B")
    ir_configured = IntelligenceRequirement(
        name="高频跟踪",
        content_spec="主题",
        status=IntelligenceRequirementStatus.ACTIVE,
        collection_frequency="1h",
        event_freshness="7d",
        valid_from=date(2026, 9, 15),
        valid_until=date(2026, 12, 31),
        sources=[source],
    )
    ir_default = IntelligenceRequirement(
        name="默认",
        content_spec="主题",
        status=IntelligenceRequirementStatus.DRAFT,
    )
    db_session.add_all([source, ir_configured, ir_default])
    db_session.flush()

    listing = inbox_client.get("/requirements")

    assert "频率" in listing.text
    assert "事件时效" in listing.text
    assert "信源" in listing.text
    assert "生效窗口" in listing.text
    assert "1h" in listing.text
    assert "7d" in listing.text
    assert "W 公司" in listing.text
    assert "2026-12-31" in listing.text
    assert "默认" in listing.text  # 未配置频率的 IR 显示默认
    assert "不限" in listing.text
    assert "全部" in listing.text
    assert "常驻" in listing.text


def test_requirement_detail_shows_config_row(inbox_client: TestClient, db_session) -> None:
    """详情页头部展示四项配置行。"""
    from datetime import date

    ir = IntelligenceRequirement(
        name="高频跟踪",
        content_spec="主题",
        status=IntelligenceRequirementStatus.ACTIVE,
        collection_frequency="1h",
        event_freshness="7d",
        valid_until=date(2026, 12, 31),
    )
    db_session.add(ir)
    db_session.flush()

    detail = inbox_client.get(f"/requirements/{ir.id}")

    assert "采集配置" in detail.text
    assert "1h" in detail.text
    assert "7d" in detail.text
    assert "2026-12-31" in detail.text


def test_requirement_create_with_config(inbox_client: TestClient, db_session) -> None:
    """新建表单带四项配置：落账读取。"""
    source = Source(name="W 公司", type=SourceType.COMPANY, confirmed=True, credit="B")
    db_session.add(source)
    db_session.flush()

    response = inbox_client.post(
        "/requirements",
        data={
            "name": "高频跟踪",
            "content_spec": "主题",
            "collection_frequency": "1h",
            "event_freshness": "7d",
            "valid_from": "2026-09-15",
            "valid_until": "2026-12-31",
            "source_ids": [str(source.id)],
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    ir_id = int(response.headers["location"].rsplit("/", 1)[-1])
    ir = db_session.get(IntelligenceRequirement, ir_id)
    assert ir is not None
    assert ir.collection_frequency == "1h"
    assert ir.event_freshness == "7d"
    assert ir.valid_until.isoformat() == "2026-12-31"
    assert len(ir.sources) == 1
    assert ir.sources[0].name == "W 公司"


def test_requirement_create_rejects_invalid_frequency(inbox_client: TestClient, db_session) -> None:
    """新建表单：频率格式非法回显错误。"""
    response = inbox_client.post(
        "/requirements",
        data={"name": "test", "content_spec": "主题", "collection_frequency": "一周内"},
    )

    assert "采集频率格式非法" in response.text
    assert db_session.scalars(select(IntelligenceRequirement)).first() is None


def test_requirement_config_update_while_active(inbox_client: TestClient, db_session) -> None:
    """激活态可编辑采集配置，落账读取。"""
    from datetime import date

    source = Source(name="W 公司", type=SourceType.COMPANY, confirmed=True, credit="B")
    ir = IntelligenceRequirement(
        name="跟踪",
        content_spec="主题",
        status=IntelligenceRequirementStatus.ACTIVE,
    )
    db_session.add_all([source, ir])
    db_session.flush()

    response = inbox_client.post(
        f"/requirements/{ir.id}/config",
        data={
            "collection_frequency": "6h",
            "event_freshness": "24h",
            "valid_from": "2026-09-15",
            "valid_until": "2026-12-31",
            "source_ids": [str(source.id)],
        },
        follow_redirects=True,
    )

    assert "采集配置已保存" in response.text
    db_session.expire_all()
    refreshed = db_session.get(IntelligenceRequirement, ir.id)
    assert refreshed is not None
    assert refreshed.collection_frequency == "6h"
    assert refreshed.event_freshness == "24h"
    assert refreshed.valid_from == date(2026, 9, 15)
    assert refreshed.valid_until == date(2026, 12, 31)
    assert len(refreshed.sources) == 1


def test_requirement_config_update_blocked_when_not_active(
    inbox_client: TestClient, db_session
) -> None:
    """非激活态不可编辑采集配置。"""
    ir = IntelligenceRequirement(
        name="test", content_spec="主题", status=IntelligenceRequirementStatus.DRAFT
    )
    db_session.add(ir)
    db_session.flush()

    response = inbox_client.post(
        f"/requirements/{ir.id}/config",
        data={"collection_frequency": "1h"},
        follow_redirects=True,
    )

    assert "仅激活态可编辑采集配置" in response.text
    db_session.expire_all()
    refreshed = db_session.get(IntelligenceRequirement, ir.id)
    assert refreshed is not None
    assert refreshed.collection_frequency is None


def test_requirement_config_update_empty_valid_until_means_standing(
    inbox_client: TestClient, db_session
) -> None:
    """截止日留空 = 常驻：提交空 valid_until 清空既有截止日。"""
    from datetime import date

    ir = IntelligenceRequirement(
        name="test",
        content_spec="主题",
        status=IntelligenceRequirementStatus.ACTIVE,
        valid_until=date(2026, 12, 31),
    )
    db_session.add(ir)
    db_session.flush()

    inbox_client.post(
        f"/requirements/{ir.id}/config",
        data={"valid_until": ""},
        follow_redirects=True,
    )

    db_session.expire_all()
    refreshed = db_session.get(IntelligenceRequirement, ir.id)
    assert refreshed is not None
    assert refreshed.valid_until is None


# ---- IIH-01.13 信源画像页 ----


def test_source_detail_unconfirmed_shows_pending_state(
    inbox_client: TestClient, db_session
) -> None:
    """待确认信源不建画像：页面只示待确认说明（decision-05）。"""
    source = Source(name="行业媒体 A", type=SourceType.MEDIA, confirmed=False)
    db_session.add(source)
    db_session.flush()

    response = inbox_client.get(f"/sources/{source.id}")

    assert response.status_code == 200
    assert "待确认" in response.text
    assert "信源信用" not in response.text  # 不入池、不记账


def test_source_detail_shows_credit_history_and_participation(
    inbox_client: TestClient, db_session
) -> None:
    """画像页：信用档 + 调整历史（可重放）+ 参与条目（转引链出现即计）。"""
    item = _seed_verified_item(db_session)
    source = item.source
    assert source is not None
    source.credit = "B"
    feedback = Feedback(item=item, feedback_type=FeedbackType.VALID, reason="快捷 · 有效")
    db_session.add(feedback)
    db_session.flush()
    db_session.add(
        CreditAdjustment(
            source=source,
            feedback=feedback,
            delta=1,
            score_after=1,
            grade_after="B",
            formula_version=SOURCE_CREDIT_FORMULA_VERSION,
        )
    )
    db_session.flush()

    response = inbox_client.get(f"/sources/{source.id}")

    assert response.status_code == 200
    assert "信源信用" in response.text
    assert "+1（有效）" in response.text  # 奖惩
    assert "1.00" in response.text  # 累计分快照
    assert "source_credit_v1" in response.text  # 公式版本（可重放）
    assert "W 公司公告：与 Z 集团签署合资协议" in response.text  # 参与条目
    assert "出处信源" in response.text


def test_source_detail_404_for_unknown(inbox_client: TestClient) -> None:
    assert inbox_client.get("/sources/9999").status_code == 404


# ---- IIH-05.01 待确认信源确认闭环 ----


def _seed_pending_with_item(
    db_session, *, source_name: str = "矿业装备出口观察"
) -> IntelligenceItem:
    """预置待确认信源（素材归因补记产生）+ 归因到它的既有条目（单节点转引链）。"""
    medium = db_session.scalars(select(Medium).where(Medium.code == "meeting_discussion")).one()
    modality = db_session.scalars(select(Modality).where(Modality.code == "text")).one()
    source = Source(name=source_name, type=SourceType.MEDIA, confirmed=False)
    item = IntelligenceItem(
        statement="行业大会传出电驱矿卡降价信号",
        status=ItemStatus.LEAD,
        mode=ItemMode.MANUAL,
        medium=medium,
        modality=modality,
        collected_at=datetime(2026, 9, 15, 9, 0, tzinfo=UTC),
        original_snapshot="行业大会纪要原文",
        source=source,
    )
    db_session.add_all([source, item])
    db_session.flush()
    db_session.add(
        ProvenanceChainNode(
            item=item,
            source=source,
            modality=modality,
            medium=medium,
            collected_at=datetime(2026, 9, 15, 9, 0, tzinfo=UTC),
        )
    )
    db_session.flush()
    return item


def test_confirm_pending_source_end_to_end(inbox_client: TestClient, db_session) -> None:
    """对应 IIH-05.01 AC#1：信源库确认 + 初始档 → 入池、建画像、可被需求绑定。"""
    item = _seed_pending_with_item(db_session)
    source = item.source
    assert source is not None

    response = inbox_client.post(
        f"/sources/{source.id}/confirm",
        data={"initial_credit": "B", "next": "/sources"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "已确认入信源库" in response.text  # flash
    db_session.expire_all()
    confirmed = db_session.get(Source, source.id)
    assert confirmed is not None
    assert confirmed.confirmed is True
    assert confirmed.credit == "B"

    detail = inbox_client.get(f"/sources/{source.id}")
    assert "信源信用" in detail.text  # 确认即建画像（画像页开放）

    # 可被情报需求绑定（confirmed 边界放开）
    ir_response = inbox_client.post(
        "/requirements",
        data={
            "name": "跟踪行业动态",
            "content_spec": "主题：矿山装备",
            "source_ids": [str(source.id)],
        },
        follow_redirects=False,
    )
    assert ir_response.status_code == 303
    ir = db_session.scalars(select(IntelligenceRequirement)).one()
    assert [s.id for s in ir.sources] == [source.id]


def test_reject_pending_source_leaves_audit_trail(inbox_client: TestClient, db_session) -> None:
    """对应 IIH-05.01 AC#2：拒绝 → 不入池、留痕可见，既有条目不受影响。"""
    item = _seed_pending_with_item(db_session)
    source = item.source
    assert source is not None
    item_id, statement = item.id, item.statement

    response = inbox_client.post(
        f"/sources/{source.id}/reject", data={"next": "/sources"}, follow_redirects=True
    )

    assert response.status_code == 200
    assert "已拒绝" in response.text  # 拒绝留痕可见（待确认区 pill + flash）
    db_session.expire_all()
    rejected = db_session.get(Source, source.id)
    assert rejected is not None
    assert rejected.confirmed is False  # 不入池
    assert rejected.rejected_at is not None

    refreshed = db_session.get(IntelligenceItem, item_id)  # 既有条目不受影响
    assert refreshed is not None
    assert refreshed.source_id == source.id
    assert refreshed.statement == statement


def test_confirm_entry_points_replace_placeholders(inbox_client: TestClient, db_session) -> None:
    """对应 IIH-05.01 DoD#2：四处「确认功能即将上线」占位全部替换为确认入口。"""
    item = _seed_pending_with_item(db_session)
    source = item.source
    assert source is not None
    undetermined = _seed_undetermined_item(db_session, confirmed=False, name="Y 公司")

    sources_page = inbox_client.get("/sources")
    assert "确认功能即将上线" not in sources_page.text
    assert ">确认</button>" in sources_page.text

    inbox_page = inbox_client.get("/")
    assert "确认功能即将上线" not in inbox_page.text
    assert ">确认</button>" in inbox_page.text

    profile = inbox_client.get(f"/sources/{source.id}")
    assert "确认功能即将上线" not in profile.text
    assert ">确认</button>" in profile.text

    item_detail = inbox_client.get(f"/items/{undetermined.id}")
    assert "确认功能即将上线" not in item_detail.text
    assert "去确认" in item_detail.text


def test_confirm_with_illegal_credit_redirects_with_err(
    inbox_client: TestClient, db_session
) -> None:
    """支撑：初始档非法经记账层校验驳回，错误回显、状态不变。"""
    item = _seed_pending_with_item(db_session)
    source = item.source
    assert source is not None

    response = inbox_client.post(
        f"/sources/{source.id}/confirm",
        data={"initial_credit": "X", "next": "/sources"},
        follow_redirects=True,
    )

    assert "初始信用档不合法" in response.text
    db_session.expire_all()
    unchanged = db_session.get(Source, source.id)
    assert unchanged is not None
    assert unchanged.confirmed is False


def test_confirm_next_redirect_is_site_path_only(inbox_client: TestClient, db_session) -> None:
    """支撑：回跳白名单——站外 next 落回默认页（防开放重定向）。"""
    item = _seed_pending_with_item(db_session)
    source = item.source
    assert source is not None

    response = inbox_client.post(
        f"/sources/{source.id}/confirm",
        data={"initial_credit": "C", "next": "https://evil.example"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith("/sources")


def test_confirm_with_rename_end_to_end(inbox_client: TestClient, db_session) -> None:
    """对应 IIH-05.01 AC#4：确认时修正名（未撞名）→ 以新名入池。"""
    item = _seed_pending_with_item(db_session, source_name="三一")
    source = item.source
    assert source is not None

    response = inbox_client.post(
        f"/sources/{source.id}/confirm",
        data={"name": "三一重工", "initial_credit": "B", "next": "/sources"},
        follow_redirects=True,
    )

    assert "已确认入信源库：三一重工" in response.text
    db_session.expire_all()
    confirmed = db_session.get(Source, source.id)
    assert confirmed is not None
    assert confirmed.name == "三一重工"
    assert confirmed.confirmed is True


def test_confirm_rename_merges_into_confirmed_end_to_end(
    inbox_client: TestClient, db_session
) -> None:
    """对应 IIH-05.01 AC#4：撞既有已确认信源名（三一 → 三一集团）→ 并入该信源。"""
    existing = Source(name="三一集团", type=SourceType.COMPANY, confirmed=True, credit="A")
    db_session.add(existing)
    db_session.flush()
    item = _seed_pending_with_item(db_session, source_name="三一")
    pending = item.source
    assert pending is not None

    response = inbox_client.post(
        f"/sources/{pending.id}/confirm",
        data={"name": "三一集团", "initial_credit": "C", "next": "/sources"},
        follow_redirects=True,
    )

    assert "已并入既有信源：三一集团" in response.text
    db_session.expire_all()
    assert db_session.get(Source, pending.id) is None  # 待确认行删除
    refreshed = db_session.get(IntelligenceItem, item.id)
    assert refreshed is not None
    assert refreshed.source_id == existing.id  # 既有条目并入目标信源
    assert db_session.get(Source, existing.id).credit == "A"  # 信用档沿用目标


def test_confirm_with_type_correction_end_to_end(inbox_client: TestClient, db_session) -> None:
    """对应 IIH-05.01 AC#4：确认时可修正类型（提取为媒体 → 修正为公司）。"""
    item = _seed_pending_with_item(db_session, source_name="三一")
    source = item.source
    assert source is not None

    response = inbox_client.post(
        f"/sources/{source.id}/confirm",
        data={"name": "三一", "source_type": "company", "initial_credit": "B", "next": "/sources"},
        follow_redirects=True,
    )

    assert "已确认入信源库" in response.text
    db_session.expire_all()
    confirmed = db_session.get(Source, source.id)
    assert confirmed is not None
    assert confirmed.type is SourceType.COMPANY


def test_confirm_rename_alias_visible_on_profile(inbox_client: TestClient, db_session) -> None:
    """对应 IIH-05.01 AC#5：确认改名后旧名留档别名，画像页可见。"""
    item = _seed_pending_with_item(db_session, source_name="三一")
    source = item.source
    assert source is not None

    inbox_client.post(
        f"/sources/{source.id}/confirm",
        data={"name": "三一重工", "initial_credit": "B", "next": "/sources"},
        follow_redirects=True,
    )

    detail = inbox_client.get(f"/sources/{source.id}")
    assert "别名" in detail.text
    assert '<span class="pill">三一</span>' in detail.text


def test_sources_list_shows_alias_pills(sources_client: TestClient, db_session) -> None:
    """信源库列表：主体名后内联别名 pill（仅有别名时出现）。"""
    holder = Source(name="三一集团", type=SourceType.COMPANY, confirmed=True, credit="A")
    db_session.add_all([holder, SourceAlias(source=holder, name="三一")])
    db_session.flush()

    listing = sources_client.get("/sources")

    assert '<span class="pill">三一</span>' in listing.text


def test_rejected_source_leaves_pending_list_and_resurfaces(
    inbox_client: TestClient, db_session
) -> None:
    """拒绝即出待确认队列；再归因重捞入队，行内提示「曾拒 ×1」。"""
    item = _seed_pending_with_item(db_session, source_name="行业媒体 B")
    source = item.source
    assert source is not None

    inbox_client.post(
        f"/sources/{source.id}/reject", data={"next": "/sources"}, follow_redirects=True
    )

    dequeued = inbox_client.get("/sources")
    assert "行业媒体 B" not in dequeued.text  # 出队
    assert "曾拒 ×" not in dequeued.text

    source.rejected_at = None  # 重捞（执行器路径由状态机单测覆盖）；拒绝事件已由上方 POST 留痕
    db_session.flush()

    resurfaced = inbox_client.get("/sources")
    assert "行业媒体 B" in resurfaced.text
    assert "曾拒 ×1" in resurfaced.text


# ---- IIH-01.13 流水线 UI 触发（浏览器端到端） ----

ENTRY_URL = "https://w-mining.example/news"
ARTICLE_URL = "https://w-mining.example/news/2026/jv-agreement"

HTML_ENTRY_LISTING = """
<html><head><title>W 公司新闻</title></head><body>
  <main>
    <h1>新闻</h1>
    <a href="/news/2026/jv-agreement">W 公司与 Z 集团签署合资协议</a>
  </main>
</body></html>
"""

HTML_ARTICLE_PAGE = """
<html><head><title>W 公司</title></head><body>
  <main>
    <p>W 公司公告：与 Z 集团签署合资协议，Q4 设立合资公司。</p>
  </main>
</body></html>
"""


def test_pipeline_button_cold_start_to_rated_inbox(db_session, monkeypatch) -> None:
    """对应 IIH-01.13 AC#1：纯浏览器冷启动→立即运行一轮→收件箱见评级条目（两跳采集）。"""
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as client:
        app.state.session_factory = sessionmaker(
            bind=db_session.bind, join_transaction_mode="create_savepoint"
        )
        client.post(
            "/sources",
            data={
                "source_name": "W 公司",
                "source_type": "company",
                "outlet_name": "官网",
                "outlet_entry": ENTRY_URL,
                "initial_credit": "B",
            },
            follow_redirects=True,
        )
        ir_id = _create_ir_via_form(client)
        client.post(f"/requirements/{ir_id}/action", data={"action": "activate"})

        extraction = StatementExtractionResult(
            statement="W 公司公告：与 Z 集团签署合资协议，Q4 设立合资公司",
            rationale="文章公告段主体陈述",
        )
        judgment = ReviewJudgmentResult(
            decision="pass",
            reason_type=None,
            matched_requirement_id=ir_id,
            rationale="陈述主题命中激活需求「跟踪 W 公司」",
        )
        pages = {ENTRY_URL: HTML_ENTRY_LISTING, ARTICLE_URL: HTML_ARTICLE_PAGE}
        monkeypatch.setattr(
            "iih.agents.llm.make_llm_client",
            lambda settings: make_fake_llm_dispatch(make_selection_article(), extraction, judgment),
        )
        monkeypatch.setattr("iih.pipeline.fetch", lambda url: pages[url])
        monkeypatch.setattr(
            "iih.tools.snapshot_store.make_snapshot_store", lambda settings: FakeSnapshotStore()
        )

        response = client.post("/pipeline/run", follow_redirects=True)

    assert response.status_code == 200
    assert "运行一轮完成" in response.text  # flash 摘要
    assert "任务 1（新建 1" in response.text
    assert "已核实 1、存疑 0" in response.text
    assert "W 公司公告：与 Z 集团签署合资协议，Q4 设立合资公司" in response.text  # 收件箱待反馈
    assert "B2" in response.text  # 二维评级
    item = db_session.scalars(select(IntelligenceItem)).unique().one()
    assert item.status is ItemStatus.VERIFIED
    assert item.rating == "B2"
    assert item.original_url == ARTICLE_URL  # 原文链接锚定文章页
    assert item.snapshot_object_key is not None


def test_pipeline_button_busy_flashes_hint(db_session) -> None:
    """上一轮未完（锁被占）→ 回首页提示，不重复执行。"""
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as client:
        app.state.pipeline_lock.acquire()  # 模拟上一轮仍在运行

        response = client.post("/pipeline/run", follow_redirects=True)

    assert response.status_code == 200
    assert "上一轮仍在运行" in response.text


# ---- IIH-01.13 存疑补救：收件箱指向 / 补设档 / 重核（偏差 #5、#6） ----


def _seed_undetermined_item(
    db_session, *, credit: str | None = None, confirmed: bool = True, name: str = "W 公司"
) -> IntelligenceItem:
    """预置一条存疑条目：单节点转引链 + 存疑核实记录（R 空）。"""
    medium = db_session.scalars(select(Medium).where(Medium.code == "internet")).one()
    modality = db_session.scalars(select(Modality).where(Modality.code == "webpage")).one()
    source = Source(name=name, type=SourceType.COMPANY, confirmed=confirmed, credit=credit)
    item = IntelligenceItem(
        statement="W 公司公告：与 Z 集团签署合资协议",
        status=ItemStatus.UNDETERMINED,
        mode=ItemMode.AUTOMATED,
        medium=medium,
        modality=modality,
        collected_at=datetime(2026, 9, 14, 10, 0, tzinfo=UTC),
        original_snapshot="正文",
        source=source,
    )
    db_session.add_all([source, item])
    db_session.flush()
    db_session.add(
        ProvenanceChainNode(
            item=item,
            source=source,
            modality=modality,
            medium=medium,
            collected_at=datetime(2026, 9, 14, 10, 0, tzinfo=UTC),
        )
    )
    db_session.add(
        VerificationRecord(
            item=item,
            outcome=VerificationOutcome.UNDETERMINED,
            independent_source_count=1,
            source_reliability=None,
            content_credibility=None,
            rating=None,
            formula_version=None,
            rationale="信源画像未设信用档，无法评定内容可信度",
        )
    )
    db_session.flush()
    return item


def test_inbox_points_to_undetermined_items(inbox_client: TestClient, db_session) -> None:
    """对应偏差 #5：运行结果含存疑时收件箱显式指向，不再「结果消失」。"""
    empty = inbox_client.get("/")
    assert "待复核（存疑）" not in empty.text

    _seed_undetermined_item(db_session)

    response = inbox_client.get("/")

    assert "待复核（存疑）" in response.text
    assert "存疑 1 条" in response.text
    assert 'href="/items?status=undetermined"' in response.text


def test_source_credit_set_via_profile_page(sources_client: TestClient, db_session) -> None:
    """对应偏差 #6：画像页人工补设/调整信用档，非法值拦截。"""
    source = Source(name="W 公司", type=SourceType.COMPANY, confirmed=True)
    db_session.add(source)
    db_session.flush()

    blocked = sources_client.post(f"/sources/{source.id}/credit", data={"credit": "X"})
    assert "信用档需为 A–F 或不设" in blocked.text
    assert db_session.get(Source, source.id).credit is None

    response = sources_client.post(
        f"/sources/{source.id}/credit", data={"credit": "B"}, follow_redirects=True
    )

    assert response.status_code == 200
    assert '<span class="pill rating">B</span>' in response.text
    assert "信用档已保存" in response.text  # 成功提示可见（flash）
    assert db_session.get(Source, source.id).credit == "B"


def test_source_rename_via_profile_page(sources_client: TestClient, db_session) -> None:
    """画像页主体改名：落账 + 空名/同名冲突拦截。"""
    source = Source(name="三一集图", type=SourceType.COMPANY, confirmed=True)
    other = Source(name="W 公司", type=SourceType.COMPANY, confirmed=True)
    db_session.add_all([source, other])
    db_session.flush()

    empty = sources_client.post(
        f"/sources/{source.id}/rename", data={"name": "  "}, follow_redirects=True
    )
    assert "名称不能为空" in empty.text

    dup = sources_client.post(
        f"/sources/{source.id}/rename", data={"name": "W 公司"}, follow_redirects=True
    )
    assert "已存在同名信源" in dup.text
    assert db_session.get(Source, source.id).name == "三一集图"

    ok = sources_client.post(
        f"/sources/{source.id}/rename", data={"name": "三一集团"}, follow_redirects=True
    )
    assert ok.status_code == 200
    assert "已改名：三一集团" in ok.text  # 成功提示可见（flash）
    assert db_session.get(Source, source.id).name == "三一集团"


def test_reverify_rescues_undetermined_after_credit_set(
    inbox_client: TestClient, db_session
) -> None:
    """存疑条目闭环救活：详情提示 → 未设档重核仍存疑（诚实重评）→ 补设档后重核出评级。"""
    item = _seed_undetermined_item(db_session)

    detail = inbox_client.get(f"/items/{item.id}")
    assert "重新核实" in detail.text
    assert "未设信用档" in detail.text  # 指引：先到画像页人工设档

    still_blocked = inbox_client.post(f"/items/{item.id}/reverify", follow_redirects=True)
    assert still_blocked.status_code == 200
    assert db_session.get(IntelligenceItem, item.id).status is ItemStatus.UNDETERMINED
    records = db_session.scalars(
        select(VerificationRecord).where(VerificationRecord.item_id == item.id)
    ).all()
    assert len(records) == 2  # 重评不覆盖历史：存疑记录 + 新存疑记录

    item.source.credit = "B"
    db_session.flush()
    rescued = inbox_client.post(f"/items/{item.id}/reverify", follow_redirects=True)

    assert rescued.status_code == 200
    final = db_session.get(IntelligenceItem, item.id)
    assert final.status is ItemStatus.VERIFIED
    assert final.rating == "B2"
    assert "已核实（B2）" in rescued.text  # 状态迁移轨迹
    assert rescued.text.count("（当前）") == 1  # 评级历史首行标当前
    records = db_session.scalars(
        select(VerificationRecord).where(VerificationRecord.item_id == item.id)
    ).all()
    assert len(records) == 3  # 存疑 ×2 + 已核实 ×1（版本化历史）

    blocked = inbox_client.post(f"/items/{item.id}/reverify", follow_redirects=True)
    assert "前置违反" in blocked.text  # 已核实条目不可再重核


def test_undetermined_hint_branches_by_source_confirmation(
    inbox_client: TestClient, db_session
) -> None:
    """存疑指引分流：未确认信源提示待确认（无设档入口，不指死路）；已确认未设档才指画像设档。"""
    unconfirmed = _seed_undetermined_item(db_session, confirmed=False, name="Y 公司")

    detail = inbox_client.get(f"/items/{unconfirmed.id}")

    assert "尚待确认" in detail.text
    assert "未设信用档——先到画像页" not in detail.text

    confirmed = _seed_undetermined_item(db_session)
    detail_confirmed = inbox_client.get(f"/items/{confirmed.id}")
    assert "未设信用档——先到画像页" in detail_confirmed.text


def test_rejection_reason_rendered_in_chinese(client: TestClient, db_session) -> None:
    """审查否决理由以中文上屏（条目详情 + 状态迁移轨迹），不出现原始枚举值。"""
    medium = db_session.scalars(select(Medium).where(Medium.code == "internet")).one()
    modality = db_session.scalars(select(Modality).where(Modality.code == "webpage")).one()
    item = IntelligenceItem(
        statement="与任何需求无关的陈述",
        status=ItemStatus.NOISE,
        mode=ItemMode.AUTOMATED,
        medium=medium,
        modality=modality,
        collected_at=datetime(2026, 9, 14, 10, 0, tzinfo=UTC),
        original_snapshot="正文",
    )
    db_session.add(item)
    db_session.flush()
    db_session.add(
        ReviewDecision(
            item=item,
            decision=ReviewDecisionEnum.REJECT,
            reason_type=RejectionReasonEnum.IRRELEVANT,
            rationale="与激活需求无关",
        )
    )
    db_session.commit()

    detail = client.get(f"/items/{item.id}")

    assert "否决理由：不相关" in detail.text
    assert "噪音（审查否决 · 不相关）" in detail.text
    assert "irrelevant" not in detail.text


# ---- IIH-01.13 配置自检：试采集预览不落账（偏差 #7） ----


def _probe_app(db_session, llm) -> TestClient:
    app = create_app()
    app.state.llm = llm
    app.dependency_overrides[get_session] = lambda: db_session
    return app


def _seed_probe_target(db_session) -> int:
    """预置激活需求 + 已确认信源互联网途径，返回需求 id。"""
    medium = db_session.scalars(select(Medium).where(Medium.code == "internet")).one()
    ir = IntelligenceRequirement(
        name="跟踪 W 公司",
        content_spec="主题：矿卡、订单、战略",
        status=IntelligenceRequirementStatus.ACTIVE,
    )
    source = Source(name="W 公司", type=SourceType.COMPANY, confirmed=True, credit="B")
    outlet = Outlet(
        source=source, name="官网", entry="https://w-mining.example/news", medium=medium
    )
    db_session.add_all([ir, source, outlet])
    db_session.flush()
    return ir.id


def test_requirement_probe_previews_without_landing(db_session, monkeypatch, w_extraction) -> None:
    """对应偏差 #7：试采集预览——抽取陈述 + 按本需求审查预判回显；不产生条目，计量照记。"""
    ir_id = _seed_probe_target(db_session)
    judgment = ReviewJudgmentResult(
        decision="pass",
        reason_type=None,
        matched_requirement_id=ir_id,
        rationale="陈述主题命中本需求内容规格",
    )
    app = _probe_app(
        db_session, make_fake_llm_dispatch(make_selection_self(), w_extraction, judgment)
    )
    monkeypatch.setattr("iih.web.requirements.fetch", lambda url, **kwargs: HTML_ARTICLE_PAGE)

    with TestClient(app) as client:
        response = client.post(f"/requirements/{ir_id}/probe")

    assert response.status_code == 200
    assert "采集概览" in response.text
    assert w_extraction.statement in response.text
    assert w_extraction.rationale in response.text
    assert "预判 · 命中" in response.text
    assert db_session.scalars(select(IntelligenceItem)).first() is None  # 不落账
    assert len(db_session.scalars(select(LlmCall)).all()) == 3  # 选链 + 抽取 + 预判，计量照记


def test_requirement_probe_reject_shows_chinese_reason(
    db_session, monkeypatch, w_extraction
) -> None:
    """试采集否决预判的否决理由以中文上屏，不出现原始枚举值。"""
    ir_id = _seed_probe_target(db_session)
    judgment = ReviewJudgmentResult(
        decision="reject",
        reason_type="irrelevant",
        matched_requirement_id=None,
        rationale="与需求内容规格无关",
    )
    app = _probe_app(
        db_session, make_fake_llm_dispatch(make_selection_self(), w_extraction, judgment)
    )
    monkeypatch.setattr("iih.web.requirements.fetch", lambda url, **kwargs: HTML_ARTICLE_PAGE)

    with TestClient(app) as client:
        response = client.post(f"/requirements/{ir_id}/probe")

    assert response.status_code == 200
    assert "预判 · 否决（不相关）" in response.text
    assert "irrelevant" not in response.text


def test_requirement_probe_reports_fetch_failure(db_session, monkeypatch) -> None:
    ir_id = _seed_probe_target(db_session)
    app = _probe_app(db_session, object())

    def boom(url, **kwargs):
        raise FetcherError("connect timeout")

    monkeypatch.setattr("iih.web.requirements.fetch", boom)

    with TestClient(app) as client:
        response = client.post(f"/requirements/{ir_id}/probe")

    assert response.status_code == 200
    assert "抓取失败：connect timeout" in response.text
    assert db_session.scalars(select(IntelligenceItem)).first() is None


def test_requirement_probe_without_outlets_shows_hint(db_session) -> None:
    ir = IntelligenceRequirement(
        name="跟踪 W 公司", content_spec="主题：矿卡", status=IntelligenceRequirementStatus.ACTIVE
    )
    db_session.add(ir)
    db_session.flush()
    app = _probe_app(db_session, object())

    with TestClient(app) as client:
        response = client.post(f"/requirements/{ir.id}/probe")

    assert response.status_code == 200
    assert "无已登记互联网途径" in response.text


def test_requirement_probe_blocked_for_non_active(db_session) -> None:
    """非激活态（如关闭）不允许试采集，回显错误且不触 LLM。"""
    ir = IntelligenceRequirement(
        name="跟踪 W 公司",
        content_spec="主题：矿卡",
        status=IntelligenceRequirementStatus.CLOSED,
    )
    db_session.add(ir)
    db_session.flush()
    app = _probe_app(db_session, object())

    with TestClient(app) as client:
        response = client.post(f"/requirements/{ir.id}/probe")

    assert response.status_code == 200
    assert "仅激活态可试采集" in response.text


# ---- IIH-01.15 快照对象存档与详情呈现 / IIH-01.16 需求表单引导 ----


def test_item_detail_shows_snapshot_link_not_flat_text(
    inbox_client: TestClient, db_session
) -> None:
    """对应 IIH-01.15 AC#4：自动条目快照为存档链接（不平铺）、默认视图只有陈述/评级/轨迹。"""
    item = _seed_verified_item(db_session)
    item.snapshot_object_key = "snapshots/abc.html"
    item.original_snapshot = None
    db_session.flush()

    detail = inbox_client.get(f"/items/{item.id}")

    assert f'href="/items/{item.id}/snapshot"' in detail.text
    assert "存档页" in detail.text
    assert "snapbox" not in detail.text  # 不再平铺归一化文本快照


def test_item_snapshot_route_serves_sandboxed_html(inbox_client: TestClient, db_session) -> None:
    """快照回放：对象 HTML 原样返回 + CSP sandbox（存档页脚本不得在本域执行）。"""
    app = inbox_client.app
    store = FakeSnapshotStore()
    key = store.put_html(HTML_ARTICLE_PAGE)
    app.state.snapshot_store = store
    item = _seed_verified_item(db_session)
    item.snapshot_object_key = key
    db_session.flush()

    response = inbox_client.get(f"/items/{item.id}/snapshot")
    manual = _seed_verified_item(db_session, statement="人工线索", source_name="Z 集团")

    assert response.status_code == 200
    assert response.headers["content-security-policy"] == "sandbox"
    assert "W 公司公告" in response.text  # 对象内容原样回放
    assert inbox_client.get(f"/items/{manual.id}/snapshot").status_code == 404  # 无对象快照
    assert inbox_client.get("/items/9999/snapshot").status_code == 404


def test_item_detail_manual_snapshot_collapsed(inbox_client: TestClient, db_session) -> None:
    """对应 IIH-01.15 AC#5：人工条目快照仍为提交文本（折叠呈现），不回归。"""
    item = _seed_verified_item(db_session)  # original_snapshot = 提交文本

    detail = inbox_client.get(f"/items/{item.id}")

    assert "<details><summary>提交文本</summary>" in detail.text
    assert "W 公司今日公告，与 Z 集团签署合资协议。" in detail.text


def test_requirement_form_shows_guided_placeholder(inbox_client: TestClient, db_session) -> None:
    """对应 IIH-01.16 AC#1：内容规格 placeholder 覆盖主题/关注对象/排除写法示例。"""
    ir_id = _create_ir_via_form(inbox_client)
    inbox_client.post(f"/requirements/{ir_id}/action", data={"action": "activate"})

    listing = inbox_client.get("/requirements")
    detail = inbox_client.get(f"/requirements/{ir_id}")

    for page in (listing, detail):
        assert "主题：矿卡、电动化、订单与业绩" in page.text
        assert "关注对象：W 公司及其竞争对手" in page.text
        assert "排除：招聘、营销活动" in page.text


# ---- 审查异议重审（doc-02 §6 处置通路：噪音回候选） ----


def _seed_noise_item(db_session) -> tuple[IntelligenceItem, IntelligenceRequirement]:
    """预置一条噪音条目：单节点转引链 + 原否决决策 + 激活需求 + 信源信用档 B。"""
    medium = db_session.scalars(select(Medium).where(Medium.code == "internet")).one()
    modality = db_session.scalars(select(Modality).where(Modality.code == "webpage")).one()
    source = Source(name="W 公司", type=SourceType.COMPANY, confirmed=True, credit="B")
    ir = IntelligenceRequirement(
        name="跟踪 W 公司",
        content_spec="主题：合资协议",
        status=IntelligenceRequirementStatus.ACTIVE,
    )
    item = IntelligenceItem(
        statement="W 公司公告：与 Z 集团签署合资协议",
        status=ItemStatus.NOISE,
        mode=ItemMode.AUTOMATED,
        medium=medium,
        modality=modality,
        collected_at=datetime(2026, 9, 14, 10, 0, tzinfo=UTC),
        original_snapshot="正文",
        source=source,
    )
    db_session.add_all([source, ir, item])
    db_session.flush()
    db_session.add(
        ProvenanceChainNode(
            item=item,
            source=source,
            modality=modality,
            medium=medium,
            collected_at=datetime(2026, 9, 14, 10, 0, tzinfo=UTC),
        )
    )
    db_session.add(
        ReviewDecision(
            item=item,
            decision=ReviewDecisionEnum.REJECT,
            reason_type=RejectionReasonEnum.IRRELEVANT,
            rationale="陈述与激活需求主题不相关",
        )
    )
    db_session.flush()
    return item, ir


def test_noise_detail_offers_dispute_form(inbox_client: TestClient, db_session) -> None:
    """噪音详情页提供审查异议入口（理由必填）；已核实详情不出现该选项。"""
    noise, _ir = _seed_noise_item(db_session)
    verified = _seed_verified_item(db_session, source_name="Z 集团")

    noise_detail = inbox_client.get(f"/items/{noise.id}")
    assert "审查异议" in noise_detail.text
    assert "提交异议并重审" in noise_detail.text
    assert 'name="reason" required' in noise_detail.text

    verified_detail = inbox_client.get(f"/items/{verified.id}")
    assert 'value="review_dispute"' not in verified_detail.text


def test_dispute_pass_returns_noise_to_verified(db_session) -> None:
    """异议 → 重审通过 → 候选并即时核实出评级；轨迹呈现完整往返。"""
    item, ir = _seed_noise_item(db_session)
    judgment = ReviewJudgmentResult(
        decision="pass",
        reason_type=None,
        matched_requirement_id=ir.id,
        rationale="异议成立：陈述命中需求主题",
    )
    app = create_app()
    app.state.llm = make_fake_llm_review(judgment)
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as client:
        response = client.post(
            f"/items/{item.id}/feedback",
            data={"feedback_type": "review_dispute", "reason": "该陈述明确命中需求主题"},
            follow_redirects=True,
        )

    assert response.status_code == 200
    final = db_session.get(IntelligenceItem, item.id)
    assert final.status is ItemStatus.VERIFIED
    assert final.rating == "B2"  # 单节点链 + 信源档 B → 确定性重评
    # 轨迹：噪音 → 候选（异议重审通过）→ 已核实
    assert "噪音（审查否决 · 不相关）" in response.text
    assert "候选情报（异议重审通过）" in response.text
    assert "已核实（B2）" in response.text
    decisions = db_session.scalars(
        select(ReviewDecision).where(ReviewDecision.item_id == item.id)
    ).all()
    assert len(decisions) == 2  # 否决 + 重审通过（版本化历史）
    feedback = db_session.scalars(select(Feedback).where(Feedback.item_id == item.id)).one()
    assert feedback.feedback_type is FeedbackType.REVIEW_DISPUTE
    assert feedback.reason == "该陈述明确命中需求主题"


def test_dispute_reject_keeps_noise_with_history(db_session) -> None:
    """重审维持否决：状态保持噪音，异议与维持决策均留痕（供迭代通路）。"""
    item, _ir = _seed_noise_item(db_session)
    judgment = ReviewJudgmentResult(
        decision="reject",
        reason_type="irrelevant",
        matched_requirement_id=None,
        rationale="维持：陈述仍与需求不相关",
    )
    app = create_app()
    app.state.llm = make_fake_llm_review(judgment)
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as client:
        response = client.post(
            f"/items/{item.id}/feedback",
            data={"feedback_type": "review_dispute", "reason": "我认为相关"},
            follow_redirects=True,
        )

    assert response.status_code == 200
    assert db_session.get(IntelligenceItem, item.id).status is ItemStatus.NOISE
    assert "噪音（异议重审维持 · 不相关）" in response.text
    decisions = db_session.scalars(
        select(ReviewDecision).where(ReviewDecision.item_id == item.id)
    ).all()
    assert len(decisions) == 2
    feedbacks = db_session.scalars(select(Feedback).where(Feedback.item_id == item.id)).all()
    assert len(feedbacks) == 1  # 异议记录不因维持而丢失


def test_dispute_without_reason_rejected_before_llm(inbox_client: TestClient, db_session) -> None:
    """异议理由必填：未填理由直接驳回，不触发重审。"""
    item, _ir = _seed_noise_item(db_session)

    response = inbox_client.post(
        f"/items/{item.id}/feedback",
        data={"feedback_type": "review_dispute", "reason": ""},
        follow_redirects=True,
    )

    assert "审查异议必须填写理由" in response.text
    assert db_session.get(IntelligenceItem, item.id).status is ItemStatus.NOISE
    assert db_session.scalars(select(Feedback)).first() is None
