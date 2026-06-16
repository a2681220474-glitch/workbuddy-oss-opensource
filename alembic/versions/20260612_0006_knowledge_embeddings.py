"""Add local knowledge embedding index.

Revision ID: 20260612_0006
Revises: 20260606_0005
Create Date: 2026-06-12
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260612_0006"
down_revision = "20260606_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "knowledge_embeddings" in inspector.get_table_names():
        return
    op.create_table(
        "knowledge_embeddings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(length=80), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("vector_json", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["item_id"], ["knowledge_items.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "item_id", name="uq_knowledge_embedding_item"),
    )
    op.create_index(op.f("ix_knowledge_embeddings_tenant_id"), "knowledge_embeddings", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_knowledge_embeddings_item_id"), "knowledge_embeddings", ["item_id"], unique=False)
    op.create_index(op.f("ix_knowledge_embeddings_model"), "knowledge_embeddings", ["model"], unique=False)
    op.create_index(op.f("ix_knowledge_embeddings_content_hash"), "knowledge_embeddings", ["content_hash"], unique=False)
    op.create_index(op.f("ix_knowledge_embeddings_updated_at"), "knowledge_embeddings", ["updated_at"], unique=False)
    op.create_index(op.f("ix_knowledge_embeddings_created_at"), "knowledge_embeddings", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_table("knowledge_embeddings")
