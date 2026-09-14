"""录入素材页单测（doc-07 §2.3、原型）：表单校验拦截（AC#2）、提交落账 Lead（AC#1）。"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from conftest import make_fake_llm
from iih.ledger.models import IntelligenceItem, ItemStatus, Outlet, Source, SourceType
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
