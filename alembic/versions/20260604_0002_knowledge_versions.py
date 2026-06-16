"""Add knowledge item versions.

Revision ID: 20260604_0002
Revises: 20260604_0001
Create Date: 2026-06-04
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260604_0002"
down_revision = "20260604_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "knowledge_item_versions" not in inspector.get_table_names():
        op.create_table(
            "knowledge_item_versions",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("item_id", sa.Integer(), nullable=False),
            sa.Column("version_no", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(length=240), nullable=False),
            sa.Column("answer", sa.String(), nullable=False),
            sa.Column("category", sa.String(length=80), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("change_type", sa.String(length=50), nullable=False),
            sa.Column("change_summary", sa.String(length=500), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["item_id"], ["knowledge_items.id"]),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    inspector = sa.inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes("knowledge_item_versions")}
    desired_indexes = [
        (op.f("ix_knowledge_item_versions_tenant_id"), ["tenant_id"]),
        (op.f("ix_knowledge_item_versions_item_id"), ["item_id"]),
        (op.f("ix_knowledge_item_versions_version_no"), ["version_no"]),
        (op.f("ix_knowledge_item_versions_category"), ["category"]),
        (op.f("ix_knowledge_item_versions_status"), ["status"]),
        (op.f("ix_knowledge_item_versions_change_type"), ["change_type"]),
        (op.f("ix_knowledge_item_versions_created_at"), ["created_at"]),
    ]
    for index_name, columns in desired_indexes:
        if index_name not in existing_indexes:
            op.create_index(index_name, "knowledge_item_versions", columns, unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_knowledge_item_versions_created_at"), table_name="knowledge_item_versions")
    op.drop_index(op.f("ix_knowledge_item_versions_change_type"), table_name="knowledge_item_versions")
    op.drop_index(op.f("ix_knowledge_item_versions_status"), table_name="knowledge_item_versions")
    op.drop_index(op.f("ix_knowledge_item_versions_category"), table_name="knowledge_item_versions")
    op.drop_index(op.f("ix_knowledge_item_versions_version_no"), table_name="knowledge_item_versions")
    op.drop_index(op.f("ix_knowledge_item_versions_item_id"), table_name="knowledge_item_versions")
    op.drop_index(op.f("ix_knowledge_item_versions_tenant_id"), table_name="knowledge_item_versions")
    op.drop_table("knowledge_item_versions")
