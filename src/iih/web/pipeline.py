"""流水线 Web 入口：「立即运行一轮」按钮（doc-07 §2.2 常驻监控的验收可控触发）。"""

import threading
from urllib.parse import quote_plus

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session, sessionmaker

router = APIRouter()


def run_round_with_lock(lock: threading.Lock, session_factory: sessionmaker[Session]) -> str | None:
    """持锁跑一轮流水线；锁被占（上一轮未完）时返回 None。

    Web 按钮与后台循环共用此入口，互斥防重叠；同步阻塞执行
    （FastAPI def 端点在线程池运行，不阻塞事件循环）。
    """
    if not lock.acquire(blocking=False):
        return None
    try:
        from iih.agents.llm import make_llm_client
        from iih.config import get_settings
        from iih.pipeline import run_pipeline_round
        from iih.tools.snapshot_store import make_snapshot_store

        settings = get_settings()
        summary = run_pipeline_round(
            settings=settings,
            session_factory=session_factory,
            llm=make_llm_client(settings),
            store=make_snapshot_store(settings),
        )
        return summary.flash()
    finally:
        lock.release()


@router.post("/pipeline/run")
def run_now(request: Request):
    """立即运行一轮：采集 → 审查 → 核实，完成后回首件箱并回显摘要。"""
    flash = run_round_with_lock(request.app.state.pipeline_lock, request.app.state.session_factory)
    if flash is None:
        flash = "上一轮仍在运行，请稍后再试。"
    return RedirectResponse("/?flash=" + quote_plus(flash), status_code=303)
