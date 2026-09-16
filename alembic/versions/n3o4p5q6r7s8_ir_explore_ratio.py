"""ir explore_ratio

Revision ID: n3o4p5q6r7s8
Revises: m2n3o4p5q6r7
Create Date: 2026-09-16

IIH-05.02 池外自由探索：情报需求加 explore_ratio 字段（0–1 触发概率，None=0）。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "n3o4p5q6r7s8"
down_revision: str | None = "m2n3o4p5q6r7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "intelligence_requirement",
        sa.Column("explore_ratio", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("intelligence_requirement", "explore_ratio")
