from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from iih.config import get_settings
from iih.db import make_engine, make_session_factory
from iih.web.submissions import router as submissions_router


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = make_engine(get_settings())
        app.state.engine = engine
        app.state.session_factory = make_session_factory(engine)
        yield
        engine.dispose()

    app = FastAPI(title="智能情报中心（IIH）", lifespan=lifespan)
    app.include_router(submissions_router)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        """健康检查：连库探活。"""
        session_factory: sessionmaker[Session] = app.state.session_factory
        with session_factory() as session:
            session.execute(text("SELECT 1"))
        return {"status": "ok"}

    return app


app = create_app()
