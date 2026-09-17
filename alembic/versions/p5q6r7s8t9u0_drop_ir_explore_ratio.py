"""drop ir explore_ratio

Revision ID: p5q6r7s8t9u0
Revises: o4p5q6r7s8t9
Create Date: 2026-09-17

IIH-06.01 通路反转：探索常驻（每轮每到期需求一个探索任务），
explore_ratio 触发概率字段废弃删除。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "p5q6r7s8t9u0"
down_revision: str | None = "o4p5q6r7s8t9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("intelligence_requirement", "explore_ratio")


def downgrade() -> None:
    op.add_column(
        "intelligence_requirement",
        sa.Column("explore_ratio", sa.Float(), nullable=True),
    )
