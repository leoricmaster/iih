"""feedback_type duplicate_noise→noise

Revision ID: s8t9u0v1w2x3
Revises: r7s8t9u0v1w2
Create Date: 2026-09-17

IIH-06.04：反馈类型「重复 / 噪音」合并为「噪音」（重复从属噪音，
doc-02 §174），枚举存值 duplicate_noise → noise，存量数据同步。
"""

from collections.abc import Sequence

from alembic import op

revision: str = "s8t9u0v1w2x3"
down_revision: str | None = "r7s8t9u0v1w2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE feedback SET feedback_type = 'noise' WHERE feedback_type = 'duplicate_noise'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE feedback SET feedback_type = 'duplicate_noise' WHERE feedback_type = 'noise'"
    )
