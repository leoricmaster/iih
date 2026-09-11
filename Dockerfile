FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

# 干净环境一条命令重建：启动即迁移，随后拉起服务（doc-08 #4）
CMD ["sh", "-c", "alembic upgrade head && uvicorn iih.web.app:app --host 0.0.0.0 --port 8000"]
