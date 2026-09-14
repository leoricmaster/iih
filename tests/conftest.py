"""测试基建：独立测试库（iih_test），会话级 Alembic 建表，每测试事务回滚；LLM 客户端替身。"""

from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from iih.agents.collector import AttributionResult, StatementExtractionResult
from iih.agents.reviewer import ReviewJudgmentResult
from iih.config import get_settings

TEST_DB_NAME = "iih_test"


def make_fake_llm(
    attribution: AttributionResult, prompt_tokens: int = 120, completion_tokens: int = 60
):
    """instructor 客户端替身：chat.completions.create_with_completion 返回 (归因, 补全)。"""

    class Completions:
        def create_with_completion(self, *, response_model, messages, **kwargs):
            assert response_model is AttributionResult
            return attribution, SimpleNamespace(
                usage=SimpleNamespace(
                    prompt_tokens=prompt_tokens, completion_tokens=completion_tokens
                )
            )

    return SimpleNamespace(chat=SimpleNamespace(completions=Completions()))


def make_fake_llm_extraction(
    extraction: StatementExtractionResult, prompt_tokens: int = 200, completion_tokens: int = 80
):
    """instructor 替身：返回 StatementExtractionResult。"""

    class Completions:
        def create_with_completion(self, *, response_model, messages, **kwargs):
            assert response_model is StatementExtractionResult
            return extraction, SimpleNamespace(
                usage=SimpleNamespace(
                    prompt_tokens=prompt_tokens, completion_tokens=completion_tokens
                )
            )

    return SimpleNamespace(chat=SimpleNamespace(completions=Completions()))


def make_fake_llm_review(
    judgment: ReviewJudgmentResult, prompt_tokens: int = 150, completion_tokens: int = 70
):
    """instructor 替身：返回 ReviewJudgmentResult。"""

    class Completions:
        def create_with_completion(self, *, response_model, messages, **kwargs):
            assert response_model is ReviewJudgmentResult
            return judgment, SimpleNamespace(
                usage=SimpleNamespace(
                    prompt_tokens=prompt_tokens, completion_tokens=completion_tokens
                )
            )

    return SimpleNamespace(chat=SimpleNamespace(completions=Completions()))


@pytest.fixture
def w_attribution() -> AttributionResult:
    return AttributionResult(
        source_name="W 公司",
        source_type="company",
        outlet_name="渠道大会现场",
        rationale="陈述主体为 W 公司，发布场景为渠道大会",
    )


@pytest.fixture
def fake_llm(w_attribution: AttributionResult):
    return make_fake_llm(w_attribution)


@pytest.fixture
def w_extraction() -> StatementExtractionResult:
    return StatementExtractionResult(
        statement="W 公司公告：与 Z 集团签署合资协议，Q4 设立合资公司",
        rationale="页面首屏公告区主体陈述，事实性强、时效近",
    )


@pytest.fixture
def fake_extraction_llm(w_extraction: StatementExtractionResult):
    return make_fake_llm_extraction(w_extraction)


@pytest.fixture
def w_review_pass_factory():
    """工厂：构造通过路径的 ReviewJudgmentResult，需传入实际 IR id。"""

    def _make(matched_requirement_id: int) -> ReviewJudgmentResult:
        return ReviewJudgmentResult(
            decision="pass",
            reason_type=None,
            matched_requirement_id=matched_requirement_id,
            rationale="陈述主题为 W 公司合资，命中激活需求「跟踪 W 公司」",
        )

    return _make


@pytest.fixture
def w_review_reject_irrelevant() -> ReviewJudgmentResult:
    return ReviewJudgmentResult(
        decision="reject",
        reason_type="irrelevant",
        matched_requirement_id=None,
        rationale="陈述与所有激活需求主题不相关",
    )


@pytest.fixture
def w_review_reject_invalid() -> ReviewJudgmentResult:
    return ReviewJudgmentResult(
        decision="reject",
        reason_type="invalid",
        matched_requirement_id=None,
        rationale="陈述为纯评价，非客观事实",
    )


@pytest.fixture(scope="session")
def database_url() -> str:
    """从运行时配置派生独立测试库连接串，并重建该库。"""
    url = make_url(get_settings().database_url).set(database=TEST_DB_NAME)
    server_url = url.set(database="postgres").render_as_string(hide_password=False)
    server_engine = create_engine(server_url, isolation_level="AUTOCOMMIT")
    with server_engine.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}"'))
        conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    server_engine.dispose()
    return url.render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def engine(database_url: str) -> Engine:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(cfg, "head")
    return create_engine(database_url, pool_pre_ping=True)


@pytest.fixture
def db_session(engine: Engine) -> Session:
    """每测试事务回滚：测试内的落账不留痕。"""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
