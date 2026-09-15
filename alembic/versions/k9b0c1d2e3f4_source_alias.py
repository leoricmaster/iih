"""待确认信源确认闭环（IIH-05.01）：信源别名表，确认改名/并入时旧名留档。

Revision ID: k9b0c1d2e3f4
Revises: h7a8b9c0d1e2
Create Date: 2026-09-15
"""

import sqlalchemy as sa
from alembic import op

revision: str = "k9b0c1d2e3f4"
down_revision: str | None = "h7a8b9c0d1e2"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "source_alias",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("source.id"), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_source_alias_source_id", "source_alias", ["source_id"])
    op.create_unique_constraint("uq_source_alias_name", "source_alias", ["name"])


def downgrade() -> None:
    op.drop_constraint("uq_source_alias_name", "source_alias", type_="unique")
    op.drop_index("ix_source_alias_source_id", table_name="source_alias")
    op.drop_table("source_alias")
