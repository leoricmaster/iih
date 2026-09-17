"""流水线一轮执行单测（doc-06 §2–§5、doc-07 §2.2）：全链 fake LLM、锁互斥、后台循环。"""

import asyncio
import threading

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from conftest import FakeSnapshotStore, make_fake_llm_dispatch, make_selection_article
from iih.agents.collector import StatementExtractionResult
from iih.agents.reviewer import ReviewJudgmentResult
from iih.config import get_settings
from iih.ledger.models import (
    Entry,
    IntelligenceItem,
    IntelligenceRequirement,
    IntelligenceRequirementStatus,
    ItemStatus,
    Source,
    SourceType,
)
from iih.pipeline import RoundSummary, run_pipeline_round
from iih.web.app import create_app
from iih.web.pipeline import run_round_with_lock

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

HTML_ARTICLE = """
<html><head><title>W 公司</title></head><body>
  <main>
    <p>W 公司公告：与 Z 集团签署合资协议，Q4 设立合资公司。</p>
  </main>
</body></html>
"""


def _seed_collectable_fixture(db_session) -> int:
    """激活需求 + 已设档信源采集入口，返回需求 id（供审查判定匹配）。"""
    source = Source(name="W 公司", type=SourceType.COMPANY, confirmed=True, credit="B")
    entry = Entry(source=source, entry="https://w-mining.example/news")
    ir = IntelligenceRequirement(
        name="跟踪 W 公司",
        content_spec="主题：矿卡、订单、战略",
        status=IntelligenceRequirementStatus.ACTIVE,
    )
    db_session.add_all([source, entry, ir])
    db_session.flush()
    return ir.id


def _dispatch_llm(ir_id: int):
    return make_fake_llm_dispatch(
        make_selection_article(),
        StatementExtractionResult(
            statement="W 公司公告：与 Z 集团签署合资协议，Q4 设立合资公司",
            rationale="文章公告段主体陈述",
        ),
        ReviewJudgmentResult(
            decision="pass",
            reason_type=None,
            matched_requirement_id=ir_id,
            rationale="陈述主题命中激活需求「跟踪 W 公司」",
        ),
    )


def test_round_summary_flash_counts() -> None:
    summary = RoundSummary(tasks=2, new_items=1, appended_nodes=1, review_passed=1, verified=1)

    flash = summary.flash()

    assert "任务 2（新建 1、追加节点 1、跳过 0、失败 0）" in flash
    assert "审查 1（通过 1、否决 0）" in flash
    assert "核实 1（已核实 1、存疑 0）" in flash
    assert "；失败" not in flash  # 无错误不加后缀

    summary.errors.append("抓取失败 X")
    assert "；失败 1 项" in summary.flash()


def test_run_pipeline_round_full_chain(db_session, monkeypatch) -> None:
    """一轮跑通两跳采集（fetch 替身）→ 审查 → 核实：新建线索落账至评级 B2。"""
    ir_id = _seed_collectable_fixture(db_session)
    pages = {ENTRY_URL: HTML_ENTRY_LISTING, ARTICLE_URL: HTML_ARTICLE}
    monkeypatch.setattr("iih.pipeline.fetch", lambda url: pages[url])
    session_factory = sessionmaker(bind=db_session.bind, join_transaction_mode="create_savepoint")

    summary = run_pipeline_round(
        settings=get_settings(),
        session_factory=session_factory,
        llm=_dispatch_llm(ir_id),
        store=FakeSnapshotStore(),
    )

    assert summary.tasks == 1
    assert summary.new_items == 1
    assert summary.review_passed == 1
    assert summary.verified == 1
    assert summary.errors == []
    item = db_session.scalars(select(IntelligenceItem)).unique().one()
    assert item.status is ItemStatus.VERIFIED
    assert item.rating == "B2"
    assert item.mode.value == "automated"
    assert item.original_url == ARTICLE_URL  # 两跳：原文链接锚定文章页
    assert item.snapshot_object_key is not None  # 快照对象已存档


def test_run_pipeline_round_without_tasks_is_noop(db_session) -> None:
    """无激活需求、无途径：一轮空跑不报错。"""
    summary = run_pipeline_round(
        settings=get_settings(),
        session_factory=sessionmaker(
            bind=db_session.bind, join_transaction_mode="create_savepoint"
        ),
        llm=object(),
    )

    assert summary.tasks == 0
    assert summary.new_items == 0
    assert summary.review_passed == 0
    assert summary.verified == 0


def test_run_round_with_lock_skips_when_busy(db_session) -> None:
    lock = threading.Lock()
    lock.acquire()  # 模拟上一轮仍在运行

    result = run_round_with_lock(lock, sessionmaker(bind=db_session.bind))

    assert result is None


def test_lifespan_pipeline_loop_follows_interval(db_session, monkeypatch) -> None:
    """interval=0 关闭后台循环；>0 启动常驻监控（doc-07 §2.2）。"""
    import iih.web.app as web_app_module

    calls: list[int] = []

    async def spy(app, interval: int) -> None:
        calls.append(interval)
        await asyncio.sleep(interval)

    monkeypatch.setattr(web_app_module, "_pipeline_loop", spy)

    off_settings = get_settings().model_copy(update={"pipeline_interval_seconds": 0})
    monkeypatch.setattr(web_app_module, "get_settings", lambda: off_settings)
    with TestClient(web_app_module.create_app()):
        assert calls == []

    on_settings = get_settings().model_copy(update={"pipeline_interval_seconds": 3600})
    monkeypatch.setattr(web_app_module, "get_settings", lambda: on_settings)
    with TestClient(create_app()):
        assert calls == [3600]


def test_run_pipeline_round_updates_last_collected_at(db_session, monkeypatch) -> None:
    """IIH-03.01：一轮采集完成后，被派单过的 IR 更新 last_collected_at。"""
    ir_id = _seed_collectable_fixture(db_session)
    pages = {ENTRY_URL: HTML_ENTRY_LISTING, ARTICLE_URL: HTML_ARTICLE}
    monkeypatch.setattr("iih.pipeline.fetch", lambda url: pages[url])
    session_factory = sessionmaker(bind=db_session.bind, join_transaction_mode="create_savepoint")

    ir = db_session.get(IntelligenceRequirement, ir_id)
    assert ir is not None
    assert ir.last_collected_at is None

    run_pipeline_round(
        settings=get_settings(),
        session_factory=session_factory,
        llm=_dispatch_llm(ir_id),
        store=FakeSnapshotStore(),
    )

    db_session.expire_all()
    refreshed = db_session.get(IntelligenceRequirement, ir_id)
    assert refreshed is not None
    assert refreshed.last_collected_at is not None
