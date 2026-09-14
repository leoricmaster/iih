"""Web 页单测（doc-07 §3、§5、原型）：录入素材、信源库、收件箱、条目详情与反馈。"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from conftest import make_fake_llm
from iih.ledger.formula import CONTENT_CREDIBILITY_FORMULA_VERSION
from iih.ledger.models import (
    Feedback,
    FeedbackType,
    IntelligenceItem,
    ItemMode,
    ItemStatus,
    Medium,
    Modality,
    Outlet,
    ProvenanceChainNode,
    Source,
    SourceType,
    VerificationOutcome,
    VerificationRecord,
)
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
    assert sources[0].credit is None
    outlets = (
        db_session.scalars(select(Outlet).where(Outlet.source_id == sources[0].id)).unique().all()
    )
    assert len(outlets) == 1
    assert outlets[0].name == "官网"
    assert outlets[0].entry == "https://w-mining.example/news"
    assert outlets[0].medium.code == "internet"


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
        },
    )
    response = sources_client.post(
        "/sources",
        data={
            "source_name": "W 公司",
            "source_type": "company",
            "outlet_name": "公众号",
            "outlet_entry": "公众号 ID：w-official",
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


def _seed_verified_item(db_session, *, statement: str = "W 公司公告：与 Z 集团签署合资协议"):
    """预置一条已核实条目：转引链单节点 + 核实记录（B2），溯源五要素齐备。"""
    medium = db_session.scalars(select(Medium).where(Medium.code == "internet")).one()
    modality = db_session.scalars(select(Modality).where(Modality.code == "webpage")).one()
    source = Source(name="W 公司", type=SourceType.COMPANY, confirmed=True, credit="B")
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
    assert "暂无已核实条目" in response.text


def test_item_detail_shows_provenance_and_rating_basis(
    inbox_client: TestClient, db_session
) -> None:
    """对应 IIH-01.04 AC#2：详情可看溯源五要素与评级依据。"""
    item = _seed_verified_item(db_session)

    response = inbox_client.get(f"/items/{item.id}")

    assert response.status_code == 200
    # 溯源五要素：载体 / 媒介 / 采集时间 / 原文快照 / 信源与途径归因
    assert "溯源五要素" in response.text
    assert "网页" in response.text  # 载体
    assert "互联网" in response.text  # 媒介
    assert "2026-09-14 10:00" in response.text  # 采集时间
    assert "W 公司今日公告，与 Z 集团签署合资协议。" in response.text  # 原文快照
    assert "W 公司 · 官网" in response.text  # 信源 / 途径归因
    # 评级依据：核实记录 + N/R/内容可信度/公式版本
    assert "评级依据" in response.text
    assert "穿透转引链得独立信源 N=1" in response.text
    assert "content_credibility_v1" in response.text


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
    assert f'href="/items/{item.id}#feedback"' in response.text  # 事实错误跳详情
