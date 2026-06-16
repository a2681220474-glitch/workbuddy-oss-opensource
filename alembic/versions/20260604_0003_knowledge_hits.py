"""Add knowledge hit records.

Revision ID: 20260604_0003
Revises: 20260604_0002
Create Date: 2026-06-04
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260604_0003"
down_revision = "20260604_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "knowledge_hits" not in inspector.get_table_names():
        op.create_table(
            "knowledge_hits",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("item_id", sa.Integer(), nullable=False),
            sa.Column("source_object_type", sa.String(length=50), nullable=False),
            sa.Column("source_object_id", sa.Integer(), nullable=False),
            sa.Column("query_text", sa.String(), nullable=False),
            sa.Column("score", sa.Integer(), nullable=False),
            sa.Column("answer_snapshot", sa.String(), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["item_id"], ["knowledge_items.id"]),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "tenant_id",
                "item_id",
                "source_object_type",
                "source_object_id",
                name="uq_knowledge_hit_source",
            ),
        )
    inspector = sa.inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes("knowledge_hits")}
    desired_indexes = [
        (op.f("ix_knowledge_hits_tenant_id"), ["tenant_id"]),
        (op.f("ix_knowledge_hits_item_id"), ["item_id"]),
        (op.f("ix_knowledge_hits_source_object_type"), ["source_object_type"]),
        (op.f("ix_knowledge_hits_source_object_id"), ["source_object_id"]),
        (op.f("ix_knowledge_hits_score"), ["score"]),
        (op.f("ix_knowledge_hits_status"), ["status"]),
        (op.f("ix_knowledge_hits_created_at"), ["created_at"]),
    ]
    for index_name, columns in desired_indexes:
        if index_name not in existing_indexes:
            op.create_index(index_name, "knowledge_hits", columns, unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_knowledge_hits_created_at"), table_name="knowledge_hits")
    op.drop_index(op.f("ix_knowledge_hits_status"), table_name="knowledge_hits")
    op.drop_index(op.f("ix_knowledge_hits_score"), table_name="knowledge_hits")
    op.drop_index(op.f("ix_knowledge_hits_source_object_id"), table_name="knowledge_hits")
    op.drop_index(op.f("ix_knowledge_hits_source_object_type"), table_name="knowledge_hits")
    op.drop_index(op.f("ix_knowledge_hits_item_id"), table_name="knowledge_hits")
    op.drop_index(op.f("ix_knowledge_hits_tenant_id"), table_name="knowledge_hits")
    op.drop_table("knowledge_hits")
