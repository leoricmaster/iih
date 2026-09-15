"""ir collection config

Revision ID: g5e6f7a8b9c0
Revises: f8b3d2a1c6e7
Create Date: 2026-09-15

IIH-03.01 需求级采集配置：情报需求加频率/事件时效/生效起止/last_collected_at 五字段，
新增情报需求-信源多对多关联表（信源绑定）。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "g5e6f7a8b9c0"
down_revision: str | None = "f8b3d2a1c6e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "intelligence_requirement",
        sa.Column("collection_frequency", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "intelligence_requirement",
        sa.Column("event_freshness", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "intelligence_requirement", sa.Column("valid_from", sa.Date(), nullable=True)
    )
    op.add_column(
        "intelligence_requirement", sa.Column("valid_until", sa.Date(), nullable=True)
    )
    op.add_column(
        "intelligence_requirement",
        sa.Column("last_collected_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "intelligence_requirement_source",
        sa.Column("requirement_id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["requirement_id"], ["intelligence_requirement.id"]),
        sa.ForeignKeyConstraint(["source_id"], ["source.id"]),
        sa.PrimaryKeyConstraint("requirement_id", "source_id"),
    )


def downgrade() -> None:
    op.drop_table("intelligence_requirement_source")
    op.drop_column("intelligence_requirement", "last_collected_at")
    op.drop_column("intelligence_requirement", "valid_until")
    op.drop_column("intelligence_requirement", "valid_from")
    op.drop_column("intelligence_requirement", "event_freshness")
    op.drop_column("intelligence_requirement", "collection_frequency")
