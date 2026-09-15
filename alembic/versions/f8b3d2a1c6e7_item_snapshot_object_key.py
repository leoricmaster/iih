"""原文快照对象存档（IIH-01.15）：加 snapshot_object_key，original_snapshot 转可空。

Revision ID: f8b3d2a1c6e7
Revises: e4d5f6a7b8c9
Create Date: 2026-09-15
"""

import sqlalchemy as sa
from alembic import op

revision: str = "f8b3d2a1c6e7"
down_revision: str | None = "e4d5f6a7b8c9"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "intelligence_item",
        sa.Column("snapshot_object_key", sa.String(120), nullable=True),
    )
    op.alter_column("intelligence_item", "original_snapshot", nullable=True)


def downgrade() -> None:
    op.alter_column("intelligence_item", "original_snapshot", nullable=False)
    op.drop_column("intelligence_item", "snapshot_object_key")
