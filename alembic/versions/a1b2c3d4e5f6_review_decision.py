"""review_decision

Revision ID: a1b2c3d4e5f6
Revises: f7a2c91b3e4d
Create Date: 2026-09-14 08:33:05.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "f7a2c91b3e4d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 审查决策记录（doc-06 §4、doc-08 #8）
    op.create_table(
        "review_decision",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column(
            "decision",
            sa.Enum("pass", "reject", name="reviewdecisionenum", native_enum=False),
            nullable=False,
        ),
        sa.Column(
            "reason_type",
            sa.Enum(
                "irrelevant",
                "duplicate",
                "invalid",
                name="rejectionreasonenum",
                native_enum=False,
            ),
            nullable=True,
        ),
        sa.Column("matched_requirement_id", sa.Integer(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["item_id"], ["intelligence_item.id"]),
        sa.ForeignKeyConstraint(
            ["matched_requirement_id"], ["intelligence_requirement.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_review_decision_item_id"),
        "review_decision",
        ["item_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_review_decision_item_id"), table_name="review_decision")
    op.drop_table("review_decision")
