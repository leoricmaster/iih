"""source discovered_entry

Revision ID: o4p5q6r7s8t9
Revises: n3o4p5q6r7s8
Create Date: 2026-09-16

IIH-05.02 补救：信源加 discovered_entry（发现来源 URL），确认时作为默认采集入口建途径。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "o4p5q6r7s8t9"
down_revision: str | None = "n3o4p5q6r7s8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "source",
        sa.Column("discovered_entry", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("source", "discovered_entry")
