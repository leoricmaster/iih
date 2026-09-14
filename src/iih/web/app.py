import asyncio
import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from iih.config import get_settings
from iih.db import make_engine, make_session_factory
from iih.web.inbox import router as inbox_router
from iih.web.items import router as items_router
from iih.web.pipeline import router as pipeline_router
from iih.web.pipeline import run_round_with_lock
from iih.web.requirements import router as requirements_router
from iih.web.sources import router as sources_router
from iih.web.submissions import router as submissions_router

logger = logging.getLogger("iih.web")

STATIC_DIR = Path(__file__).parent / "static"


async def _pipeline_loop(app: FastAPI, interval: int) -> None:
    """后台自动循环（doc-07 §2.2 常驻监控最简实现）：间隔到即跑一轮，异常记日志续跑。"""
    while True:
        await asyncio.sleep(interval)
        try:
            flash = await asyncio.to_thread(
                run_round_with_lock,
                app.state.pipeline_lock,
                app.state.session_factory,
            )
            if flash is None:
                logger.info("pipeline tick skipped: previous round still running")
            else:
                logger.info("pipeline tick: %s", flash)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("pipeline tick failed")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    engine = make_engine(settings)
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    app.state.pipeline_lock = threading.Lock()

    loop_task: asyncio.Task | None = None
    if settings.pipeline_interval_seconds > 0:
        loop_task = asyncio.create_task(_pipeline_loop(app, settings.pipeline_interval_seconds))
    yield
    if loop_task is not None:
        loop_task.cancel()
        await asyncio.gather(loop_task, return_exceptions=True)
    engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(title="智能情报中心（IIH）", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.include_router(inbox_router)
    app.include_router(items_router)
    app.include_router(submissions_router)
    app.include_router(sources_router)
    app.include_router(requirements_router)
    app.include_router(pipeline_router)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        """健康检查：连库探活。"""
        session_factory: sessionmaker[Session] = app.state.session_factory
        with session_factory() as session:
            session.execute(text("SELECT 1"))
        return {"status": "ok"}

    return app


app = create_app()
