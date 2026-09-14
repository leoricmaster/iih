"""ir and provenance chain

Revision ID: f7a2c91b3e4d
Revises: dbd4fff9cbbd
Create Date: 2026-09-14 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f7a2c91b3e4d"
down_revision: str | None = "dbd4fff9cbbd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 情报需求（doc-04 §1、doc-02 §4.1）
    op.create_table(
        "intelligence_requirement",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("content_spec", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "active",
                "paused",
                "closed",
                name="intelligencerequirementstatus",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_intelligence_requirement_status"),
        "intelligence_requirement",
        ["status"],
        unique=False,
    )

    # 转引链节点（doc-03 §六）
    op.create_table(
        "provenance_chain_node",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("outlet_id", sa.Integer(), nullable=True),
        sa.Column("modality_id", sa.Integer(), nullable=False),
        sa.Column("medium_id", sa.Integer(), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("original_url", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["item_id"], ["intelligence_item.id"]),
        sa.ForeignKeyConstraint(["source_id"], ["source.id"]),
        sa.ForeignKeyConstraint(["outlet_id"], ["outlet.id"]),
        sa.ForeignKeyConstraint(["modality_id"], ["modality.id"]),
        sa.ForeignKeyConstraint(["medium_id"], ["medium.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "item_id", "source_id", "outlet_id", name="uq_node_per_item_source_outlet"
        ),
    )
    op.create_index(
        op.f("ix_provenance_chain_node_item_id"),
        "provenance_chain_node",
        ["item_id"],
        unique=False,
    )

    # 情报条目扩展：内容指纹 + 原文链接（doc-06 §3 前置过滤）
    op.add_column(
        "intelligence_item",
        sa.Column("content_fingerprint", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "intelligence_item",
        sa.Column("original_url", sa.Text(), nullable=True),
    )
    op.create_index(
        op.f("ix_intelligence_item_content_fingerprint"),
        "intelligence_item",
        ["content_fingerprint"],
        unique=False,
    )
    # 部分唯一索引：仅 content_fingerprint IS NOT NULL 行唯一（PG 语法）
    op.create_index(
        "uq_intelligence_item_content_fingerprint",
        "intelligence_item",
        ["content_fingerprint"],
        unique=True,
        postgresql_where=sa.text("content_fingerprint IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_intelligence_item_content_fingerprint", table_name="intelligence_item")
    op.drop_index(op.f("ix_intelligence_item_content_fingerprint"), table_name="intelligence_item")
    op.drop_column("intelligence_item", "original_url")
    op.drop_column("intelligence_item", "content_fingerprint")

    op.drop_index(op.f("ix_provenance_chain_node_item_id"), table_name="provenance_chain_node")
    op.drop_table("provenance_chain_node")

    op.drop_index(op.f("ix_intelligence_requirement_status"), table_name="intelligence_requirement")
    op.drop_table("intelligence_requirement")
