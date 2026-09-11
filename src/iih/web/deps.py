"""Web 层依赖：请求级会话与 LLM 客户端注入。"""

from collections.abc import Iterator

from fastapi import Request
from instructor import Instructor
from sqlalchemy.orm import Session

from iih.agents.llm import make_llm_client
from iih.config import get_settings


def get_session(request: Request) -> Iterator[Session]:
    """请求级数据库会话。"""
    with request.app.state.session_factory() as session:
        yield session


def get_llm_client(request: Request) -> Instructor:
    """LLM 客户端：app.state 缓存（懒建），测试可直接注入替身。"""
    client = getattr(request.app.state, "llm", None)
    if client is None:
        client = make_llm_client(get_settings())
        request.app.state.llm = client
    return client
