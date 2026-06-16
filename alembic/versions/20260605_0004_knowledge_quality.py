"""Add knowledge quality governance fields.

Revision ID: 20260605_0004
Revises: 20260604_0003
Create Date: 2026-06-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260605_0004"
down_revision = "20260604_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("knowledge_items")}
    desired_columns = [
        ("review_due_at", sa.Column("review_due_at", sa.DateTime(), nullable=True)),
        ("last_reviewed_at", sa.Column("last_reviewed_at", sa.DateTime(), nullable=True)),
        (
            "quality_status",
            sa.Column("quality_status", sa.String(length=40), nullable=False, server_default="healthy"),
        ),
        ("quality_score", sa.Column("quality_score", sa.Integer(), nullable=False, server_default="80")),
    ]
    for column_name, column in desired_columns:
        if column_name not in existing_columns:
            op.add_column("knowledge_items", column)
    inspector = sa.inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes("knowledge_items")}
    desired_indexes = [
        (op.f("ix_knowledge_items_review_due_at"), ["review_due_at"]),
        (op.f("ix_knowledge_items_last_reviewed_at"), ["last_reviewed_at"]),
        (op.f("ix_knowledge_items_quality_status"), ["quality_status"]),
        (op.f("ix_knowledge_items_quality_score"), ["quality_score"]),
    ]
    for index_name, columns in desired_indexes:
        if index_name not in existing_indexes:
            op.create_index(index_name, "knowledge_items", columns, unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_knowledge_items_quality_score"), table_name="knowledge_items")
    op.drop_index(op.f("ix_knowledge_items_quality_status"), table_name="knowledge_items")
    op.drop_index(op.f("ix_knowledge_items_last_reviewed_at"), table_name="knowledge_items")
    op.drop_index(op.f("ix_knowledge_items_review_due_at"), table_name="knowledge_items")
    op.drop_column("knowledge_items", "quality_score")
    op.drop_column("knowledge_items", "quality_status")
    op.drop_column("knowledge_items", "last_reviewed_at")
    op.drop_column("knowledge_items", "review_due_at")
