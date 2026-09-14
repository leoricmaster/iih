"""feedback

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-09-14 11:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 反馈（doc-04 §1、doc-02 §6）：消费方对条目的类型化评价
    op.create_table(
        "feedback",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column(
            "feedback_type",
            sa.Enum(
                "valid",
                "factual_error",
                "duplicate_noise",
                "irrelevant",
                "outdated",
                "rating_dispute",
                name="feedbacktype",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["item_id"], ["intelligence_item.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_feedback_item_id"), "feedback", ["item_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_feedback_item_id"), table_name="feedback")
    op.drop_table("feedback")
