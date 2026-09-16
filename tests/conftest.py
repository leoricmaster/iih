"""测试基建：独立测试库（iih_test），会话级 Alembic 建表，每测试事务回滚；LLM 客户端替身。"""

import hashlib
from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from iih.agents.collector import (
    ArticleSelectionResult,
    AttributionResult,
    ExplorationAttributionResult,
    ExplorationKeywordResult,
    ExplorationResultSelectionResult,
    ManualExtractionResult,
    ManualStatement,
    StatementExtractionResult,
)
from iih.agents.reviewer import ReviewJudgmentResult
from iih.config import get_settings
from iih.tools.asr import TingwuAsrError, TranscriptionResult
from iih.tools.search import SearchResult

TEST_DB_NAME = "iih_test"


def make_manual_extraction(*statements: str) -> ManualExtractionResult:
    """纪要抽取替身：给定若干陈述文本（均无事件时间）。"""
    return ManualExtractionResult(
        statements=[ManualStatement(statement=s, rationale="纪要中的客观要点") for s in statements]
    )


def make_fake_llm_manual(
    extraction: ManualExtractionResult,
    attribution: AttributionResult,
    prompt_tokens: int = 120,
    completion_tokens: int = 60,
):
    """instructor 替身：人工路径分发（纪要抽取 / 归因）。"""
    return _make_dispatch_llm(
        {ManualExtractionResult: extraction, AttributionResult: attribution},
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )


def make_fake_llm(
    attribution: AttributionResult, prompt_tokens: int = 120, completion_tokens: int = 60
):
    """instructor 客户端替身：人工路径——抽取为恒等（提交文本整体作为一条陈述）+ 归因。"""

    class Completions:
        def create_with_completion(self, *, response_model, messages, **kwargs):
            if response_model is ManualExtractionResult:
                user = next(m["content"] for m in messages if m["role"] == "user")
                result: object = make_manual_extraction(user.split("素材文本：\n", 1)[1])
            else:
                assert response_model is AttributionResult
                result = attribution
            return result, SimpleNamespace(
                usage=SimpleNamespace(
                    prompt_tokens=prompt_tokens, completion_tokens=completion_tokens
                )
            )

    return SimpleNamespace(chat=SimpleNamespace(completions=Completions()))


class FakeSnapshotStore:
    """SnapshotStore 内存替身：内容寻址键与真实实现一致。"""

    def __init__(self) -> None:
        self.objects: dict[str, str] = {}
        self.materials: dict[str, bytes] = {}

    def put_html(self, html: str) -> str:
        digest = hashlib.sha256(html.encode("utf-8")).hexdigest()
        key = f"snapshots/{digest}.html"
        self.objects[key] = html
        return key

    def get_html(self, key: str) -> str:
        return self.objects[key]

    def put_material(self, data: bytes, ext: str) -> str:
        digest = hashlib.sha256(data).hexdigest()
        key = f"materials/{digest}.{ext}"
        self.materials[key] = data
        return key

    def get_material(self, key: str) -> bytes:
        return self.materials[key]


@pytest.fixture
def fake_snapshot_store() -> FakeSnapshotStore:
    return FakeSnapshotStore()


class FakeAsr:
    """TingwuAsr 替身：submit 派任务号并记录；check 未 finish 返回 None，finish 后出稿。"""

    def __init__(
        self,
        *,
        transcript: str = "[00:00] 发言人1：W 公司与 Z 集团签署合资协议，Q4 设立合资公司",
        duration_seconds: int = 300,
        submit_error: str = "",
        check_error: str = "",
    ) -> None:
        self.transcript = transcript
        self.duration_seconds = duration_seconds
        self.submit_error = submit_error
        self.check_error = check_error
        self.task_seq = 0
        self.submitted: list[bytes] = []
        self.attempts: list[bytes] = []  # 含失败尝试（提交即计数）
        self._done: set[str] = set()

    def submit(self, audio: bytes, filename: str) -> str:
        self.attempts.append(audio)
        if self.submit_error:
            raise TingwuAsrError(self.submit_error)
        self.task_seq += 1
        self.submitted.append(audio)
        return f"fake-task-{self.task_seq}"

    def finish(self, task_id: str) -> None:
        self._done.add(task_id)

    def check(self, task_id: str) -> TranscriptionResult | None:
        if self.check_error:
            raise TingwuAsrError(self.check_error)
        if task_id not in self._done:
            return None
        return TranscriptionResult(text=self.transcript, duration_seconds=self.duration_seconds)


@pytest.fixture
def fake_asr() -> FakeAsr:
    return FakeAsr()


def make_selection_article() -> ArticleSelectionResult:
    """选链替身：入口页为列表页，选中合资公告文章页。"""
    return ArticleSelectionResult(
        url="https://w-mining.example/news/2026/jv-agreement",
        rationale="入口页为新闻列表，选合资协议公告文章链接",
    )


def make_selection_self() -> ArticleSelectionResult:
    """选链替身：入口页本身即文章正文页（单跳回退）。"""
    return ArticleSelectionResult(url="", rationale="入口页即文章正文页")


def _make_dispatch_llm(responses: dict[type, object], prompt_tokens: int, completion_tokens: int):
    class Completions:
        def create_with_completion(self, *, response_model, messages, **kwargs):
            result = responses[response_model]
            return result, SimpleNamespace(
                usage=SimpleNamespace(
                    prompt_tokens=prompt_tokens, completion_tokens=completion_tokens
                )
            )

    return SimpleNamespace(chat=SimpleNamespace(completions=Completions()))


def make_fake_llm_collect(selection: ArticleSelectionResult, extraction: StatementExtractionResult):
    """instructor 替身：按 response_model 分发选链 / 抽取（collect_outlet 单测）。"""
    return _make_dispatch_llm(
        {ArticleSelectionResult: selection, StatementExtractionResult: extraction},
        prompt_tokens=200,
        completion_tokens=80,
    )


def make_fake_llm_explore(
    selection: ArticleSelectionResult,
    extraction: StatementExtractionResult,
    exploration_keywords: ExplorationKeywordResult,
    exploration_selection: ExplorationResultSelectionResult,
    exploration_attribution: ExplorationAttributionResult,
):
    """instructor 替身：池外探索场景——分发选链/抽取/关键词/检索结果选链/归因。"""
    return _make_dispatch_llm(
        {
            ArticleSelectionResult: selection,
            StatementExtractionResult: extraction,
            ExplorationKeywordResult: exploration_keywords,
            ExplorationResultSelectionResult: exploration_selection,
            ExplorationAttributionResult: exploration_attribution,
        },
        prompt_tokens=200,
        completion_tokens=80,
    )


def make_fake_tavily(results: list[SearchResult]):
    """Tavily search 替身：固定结果列表，不发起真实 HTTP。"""

    def _fake_search(query, *, api_key, max_results=5, timeout=15.0):
        return list(results)

    return _fake_search


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


def make_fake_llm_dispatch(
    selection: ArticleSelectionResult,
    extraction: StatementExtractionResult,
    judgment: ReviewJudgmentResult,
):
    """instructor 替身：按 response_model 分发（选链 / 抽取 / 审查判定），供流水线全链测试。"""

    class Completions:
        def create_with_completion(self, *, response_model, messages, **kwargs):
            if response_model is ArticleSelectionResult:
                result = selection
            elif response_model is StatementExtractionResult:
                result = extraction
            else:
                assert response_model is ReviewJudgmentResult
                result = judgment
            return result, SimpleNamespace(
                usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5)
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
