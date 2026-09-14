"""verification_record

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-14 09:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 核实评级记录（doc-06 §5、doc-08 #8、doc-04 §1 推理记录）
    op.create_table(
        "verification_record",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column(
            "outcome",
            sa.Enum("verified", "undetermined", name="verificationoutcome", native_enum=False),
            nullable=False,
        ),
        sa.Column("independent_source_count", sa.Integer(), nullable=False),
        sa.Column("source_reliability", sa.String(length=1), nullable=True),
        sa.Column("content_credibility", sa.Integer(), nullable=True),
        sa.Column("rating", sa.String(length=2), nullable=True),
        sa.Column("formula_version", sa.String(length=50), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["item_id"], ["intelligence_item.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_verification_record_item_id"),
        "verification_record",
        ["item_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_verification_record_item_id"), table_name="verification_record")
    op.drop_table("verification_record")
