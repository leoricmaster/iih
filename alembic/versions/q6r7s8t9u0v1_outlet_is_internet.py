"""outlet is_internet

Revision ID: q6r7s8t9u0v1
Revises: p5q6r7s8t9u0
Create Date: 2026-09-17

IIH-06.03：Outlet.medium_id 外键 → is_internet 布尔。非互联网途径 entry
必空、medium 在 Outlet 上仅 internet 分支被使用，model 层简化为布尔。
Medium 表保留供 IntelligenceItem/Material 使用。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "q6r7s8t9u0v1"
down_revision: str | None = "p5q6r7s8t9u0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "outlet",
        sa.Column("is_internet", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute(
        "UPDATE outlet SET is_internet = ("
        "  SELECT CASE WHEN medium.code = 'internet' THEN true ELSE false END"
        "  FROM medium WHERE medium.id = outlet.medium_id"
        ")"
    )
    op.drop_constraint("outlet_medium_id_fkey", "outlet", type_="foreignkey")
    op.drop_column("outlet", "medium_id")


def downgrade() -> None:
    op.add_column(
        "outlet",
        sa.Column("medium_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key("outlet_medium_id_fkey", "outlet", "medium", ["medium_id"], ["id"])
    op.execute(
        "UPDATE outlet SET medium_id = ("
        "  CASE WHEN is_internet THEN (SELECT id FROM medium WHERE medium.code = 'internet')"
        "  ELSE (SELECT id FROM medium WHERE medium.code = 'meeting_discussion')"
        "  END"
        ")"
    )
    op.drop_column("outlet", "is_internet")
