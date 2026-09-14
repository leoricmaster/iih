"""Web 页单测（doc-07 §3、§5、原型）：录入素材、信源库、收件箱、条目详情与反馈。"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from conftest import make_fake_llm, make_fake_llm_dispatch
from iih.agents.collector import StatementExtractionResult
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
    items = db_session.scalars(select(IntelligenceItem)).all()
    assert len(items) == 1
    assert items[0].status is ItemStatus.LEAD
    assert items[0].source is not None and items[0].source.name == "W 公司"


def test_submit_with_missing_fields_is_blocked(client: TestClient, db_session) -> None:
    """对应 IIH-01.01 AC#2：必填缺失表单拦截，不生成提案。"""
    response = client.post("/submissions", data={"medium_code": "", "statement": ""})

    assert response.status_code == 200  # 重渲染表单并提示
    assert "请选择媒介" in response.text
    assert "请填写陈述内容" in response.text
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
    assert "2026-09-14 10:00" in response.text  # 采集时间
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
    assert response.headers["location"] == "http://testserver/"
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
    """草稿 → 激活 ⇄ 暂停 → 关闭（终态），迁移经提案落账（doc-02 §4.1）。"""
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
    assert 'name="action"' not in closed.text  # 终态无动作按钮

    blocked = act("activate")  # 关闭为终态：再激活被驳回并回显
    assert "前置违反" in blocked.text
    assert status() is IntelligenceRequirementStatus.CLOSED


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


# ---- IIH-01.13 流水线 UI 触发（浏览器端到端） ----

HTML_FETCH_PAGE = """
<html><head><title>W 公司</title></head><body>
  <main>
    <p>W 公司公告：与 Z 集团签署合资协议，Q4 设立合资公司。</p>
  </main>
</body></html>
"""


def test_pipeline_button_cold_start_to_rated_inbox(db_session, monkeypatch) -> None:
    """对应 IIH-01.13 AC#1：纯浏览器冷启动→立即运行一轮→收件箱见评级条目。"""
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
                "outlet_entry": "https://w-mining.example/news",
                "initial_credit": "B",
            },
            follow_redirects=True,
        )
        ir_id = _create_ir_via_form(client)
        client.post(f"/requirements/{ir_id}/action", data={"action": "activate"})

        extraction = StatementExtractionResult(
            statement="W 公司公告：与 Z 集团签署合资协议，Q4 设立合资公司",
            rationale="页面公告区主体陈述",
        )
        judgment = ReviewJudgmentResult(
            decision="pass",
            reason_type=None,
            matched_requirement_id=ir_id,
            rationale="陈述主题命中激活需求「跟踪 W 公司」",
        )
        monkeypatch.setattr(
            "iih.agents.llm.make_llm_client",
            lambda settings: make_fake_llm_dispatch(extraction, judgment),
        )
        monkeypatch.setattr("iih.pipeline.fetch", lambda url: HTML_FETCH_PAGE)

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
    assert db_session.get(Source, source.id).credit == "B"


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
    app = _probe_app(db_session, make_fake_llm_dispatch(w_extraction, judgment))
    monkeypatch.setattr("iih.web.requirements.fetch", lambda url, **kwargs: HTML_FETCH_PAGE)

    with TestClient(app) as client:
        response = client.post(f"/requirements/{ir_id}/probe")

    assert response.status_code == 200
    assert "配置自检" in response.text
    assert w_extraction.statement in response.text
    assert w_extraction.rationale in response.text
    assert "预判 · 命中" in response.text
    assert db_session.scalars(select(IntelligenceItem)).first() is None  # 不落账
    assert len(db_session.scalars(select(LlmCall)).all()) == 2  # 抽取 + 预判，计量照记


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
    app = _probe_app(db_session, make_fake_llm_dispatch(w_extraction, judgment))
    monkeypatch.setattr("iih.web.requirements.fetch", lambda url, **kwargs: HTML_FETCH_PAGE)

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
