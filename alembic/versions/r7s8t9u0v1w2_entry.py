"""entry：途径退役，采集入口落地

Revision ID: r7s8t9u0v1w2
Revises: q6r7s8t9u0v1
Create Date: 2026-09-17

IIH-06.03 第二轮：途径 Outlet 退役为采集入口 Entry（id/source_id/entry）。
线下途径（entry 为空）删除；条目与转引链节点去途径引用——溯源要素收敛为
信源 × 媒介 × 载体 × 时间，采集入口仅承载调度配置（Director 派单 URL）。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "r7s8t9u0v1w2"
down_revision: str | None = "q6r7s8t9u0v1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 先去条目/节点引用，再清理途径行（避免 FK 阻塞线下途径删除）
    op.drop_constraint("intelligence_item_outlet_id_fkey", "intelligence_item", type_="foreignkey")
    op.drop_constraint(
        "provenance_chain_node_outlet_id_fkey", "provenance_chain_node", type_="foreignkey"
    )
    op.drop_column("intelligence_item", "outlet_id")
    op.drop_constraint("uq_node_per_item_source_outlet", "provenance_chain_node", type_="unique")
    op.drop_column("provenance_chain_node", "outlet_id")
    # 同一条目同一信源至多一节点（原约束以途径区分，途径退役后按信源去重，留最早节点）
    op.execute(
        "DELETE FROM provenance_chain_node n USING provenance_chain_node m"
        " WHERE n.item_id = m.item_id AND n.source_id = m.source_id AND n.id > m.id"
    )
    op.create_unique_constraint(
        "uq_node_per_item_source", "provenance_chain_node", ["item_id", "source_id"]
    )
    # 线下途径退役：entry 为空即删
    op.execute("DELETE FROM outlet WHERE entry IS NULL")
    # 同信源同入口去重（原以 name 区分，name 退役后按 entry 去重，留最早行）
    op.execute(
        "DELETE FROM outlet o USING outlet p"
        " WHERE o.source_id = p.source_id AND o.entry = p.entry AND o.id > p.id"
    )
    op.drop_constraint("outlet_source_id_name_key", "outlet", type_="unique")
    op.alter_column("outlet", "entry", existing_type=sa.Text(), nullable=False)
    op.drop_column("outlet", "name")
    op.drop_column("outlet", "is_internet")
    op.create_unique_constraint("uq_entry_source_entry", "outlet", ["source_id", "entry"])
    op.rename_table("outlet", "entry")


def downgrade() -> None:
    op.rename_table("entry", "outlet")
    op.drop_constraint("uq_entry_source_entry", "outlet", type_="unique")
    op.add_column("outlet", sa.Column("name", sa.String(length=200), nullable=True))
    op.add_column(
        "outlet",
        sa.Column("is_internet", sa.Boolean(), nullable=True, server_default=sa.true()),
    )
    # name 以 entry 前缀 + 行号重建，保证 (source_id, name) 唯一（名称数据已随退役丢失）
    op.execute("UPDATE outlet SET name = left(entry, 180) || ' #' || id::text")
    op.execute("UPDATE outlet SET is_internet = true")
    op.alter_column("outlet", "name", existing_type=sa.String(length=200), nullable=False)
    op.alter_column("outlet", "is_internet", existing_type=sa.Boolean(), nullable=False)
    op.alter_column("outlet", "entry", existing_type=sa.Text(), nullable=True)
    op.create_unique_constraint("outlet_source_id_name_key", "outlet", ["source_id", "name"])
    op.add_column("intelligence_item", sa.Column("outlet_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "intelligence_item_outlet_id_fkey",
        "intelligence_item",
        "outlet",
        ["outlet_id"],
        ["id"],
    )
    op.add_column("provenance_chain_node", sa.Column("outlet_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "provenance_chain_node_outlet_id_fkey",
        "provenance_chain_node",
        "outlet",
        ["outlet_id"],
        ["id"],
    )
    op.create_unique_constraint(
        "uq_node_per_item_source_outlet",
        "provenance_chain_node",
        ["item_id", "source_id", "outlet_id"],
    )
    op.drop_constraint("uq_node_per_item_source", "provenance_chain_node", type_="unique")
