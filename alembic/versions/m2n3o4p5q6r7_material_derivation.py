"""material and derivation

Revision ID: m2n3o4p5q6r7
Revises: l1c2d3e4f5a6
Create Date: 2026-09-15

IIH-02.01 素材一等实体最小版：素材表（附件处理状态机）+ 派生表（逐级加工留痕），
情报条目加挂链字段（原文快照第三轨：挂素材 + 所自派生级，不内嵌快照）。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "m2n3o4p5q6r7"
down_revision: str | None = "l1c2d3e4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "material",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("modality_id", sa.Integer(), nullable=False),
        sa.Column("medium_id", sa.Integer(), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("object_key", sa.String(length=200), nullable=False),
        sa.Column("filename", sa.String(length=500), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "uploaded",
                "processing",
                "extracting",
                "completed",
                "process_failed",
                "extract_failed",
                native_enum=False,
                length=50,
            ),
            nullable=False,
        ),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("external_task_id", sa.String(length=200), nullable=True),
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
        sa.ForeignKeyConstraint(["modality_id"], ["modality.id"]),
        sa.ForeignKeyConstraint(["medium_id"], ["medium.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_material_status", "material", ["status"])
    op.create_table(
        "derivation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column(
            "producer",
            sa.Enum("tool", "agent", "human", native_enum=False, length=50),
            nullable=False,
        ),
        sa.Column("producer_ref", sa.String(length=200), nullable=False),
        sa.Column("output_text", sa.Text(), nullable=True),
        sa.Column("output_object_key", sa.String(length=200), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["material_id"], ["material.id"]),
        sa.ForeignKeyConstraint(["parent_id"], ["derivation.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_derivation_material_id", "derivation", ["material_id"])
    op.add_column(
        "intelligence_item",
        sa.Column("material_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "intelligence_item",
        sa.Column("derivation_id", sa.Integer(), nullable=True),
    )
    op.create_index("ix_intelligence_item_material_id", "intelligence_item", ["material_id"])
    op.create_foreign_key(
        "fk_intelligence_item_material",
        "intelligence_item",
        "material",
        ["material_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_intelligence_item_derivation",
        "intelligence_item",
        "derivation",
        ["derivation_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_intelligence_item_derivation", "intelligence_item", type_="foreignkey")
    op.drop_constraint("fk_intelligence_item_material", "intelligence_item", type_="foreignkey")
    op.drop_index("ix_intelligence_item_material_id", table_name="intelligence_item")
    op.drop_column("intelligence_item", "derivation_id")
    op.drop_column("intelligence_item", "material_id")
    op.drop_index("ix_derivation_material_id", table_name="derivation")
    op.drop_table("derivation")
    op.drop_index("ix_material_status", table_name="material")
    op.drop_table("material")
