"""信源拒绝留痕事件表（IIH-05.01：拒绝即出队，重捞再现带上记录）

Revision ID: l1c2d3e4f5a6
Revises: k9b0c1d2e3f4
Create Date: 2026-09-15 23:05:00

"""

import sqlalchemy as sa
from alembic import op

revision = "l1c2d3e4f5a6"
down_revision = "k9b0c1d2e3f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_rejection",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "source_id",
            sa.Integer(),
            sa.ForeignKey("source.id"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_source_rejection_source_id", "source_rejection", ["source_id"])


def downgrade() -> None:
    op.drop_index("ix_source_rejection_source_id", table_name="source_rejection")
    op.drop_table("source_rejection")
