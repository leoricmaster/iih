"""待确认信源确认闭环（IIH-05.01）：source 加 rejected_at 拒绝留痕。

Revision ID: h7a8b9c0d1e2
Revises: g5e6f7a8b9c0
Create Date: 2026-09-15
"""

import sqlalchemy as sa
from alembic import op

revision: str = "h7a8b9c0d1e2"
down_revision: str | None = "g5e6f7a8b9c0"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("source", sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("source", "rejected_at")
