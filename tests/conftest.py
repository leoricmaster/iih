"""测试基建：独立测试库（iih_test），会话级 Alembic 建表，每测试事务回滚；LLM 客户端替身。"""

from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from iih.agents.collector import AttributionResult
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
