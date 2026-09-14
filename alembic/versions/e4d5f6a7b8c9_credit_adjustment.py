"""credit_adjustment

Revision ID: e4d5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-09-14 12:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e4d5f6a7b8c9"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 信用调整记录（doc-04 §2.3、decision-04）：责任信源奖惩 + 计算/分档快照
    op.create_table(
        "credit_adjustment",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("feedback_id", sa.Integer(), nullable=False),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column("score_after", sa.Float(), nullable=False),
        sa.Column("grade_after", sa.String(length=1), nullable=False),
        sa.Column("formula_version", sa.String(length=50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["source_id"], ["source.id"]),
        sa.ForeignKeyConstraint(["feedback_id"], ["feedback.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("feedback_id"),
    )
    op.create_index(
        op.f("ix_credit_adjustment_source_id"), "credit_adjustment", ["source_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_credit_adjustment_source_id"), table_name="credit_adjustment")
    op.drop_table("credit_adjustment")
