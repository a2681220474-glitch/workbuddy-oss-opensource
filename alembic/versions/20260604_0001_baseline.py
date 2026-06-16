"""baseline schema

Revision ID: 20260604_0001
Revises:
Create Date: 2026-06-04 00:00:00
"""

from __future__ import annotations

from alembic import op
from sqlmodel import SQLModel

import apps.api.models  # noqa: F401 - ensure metadata is registered


revision = "20260604_0001"
down_revision = None
branch_labels = None
depends_on = None


BASELINE_EXCLUDED_TABLES = {
    "knowledge_item_versions",
    "knowledge_hits",
}


def upgrade() -> None:
    bind = op.get_bind()
    tables = [table for table in SQLModel.metadata.sorted_tables if table.name not in BASELINE_EXCLUDED_TABLES]
    SQLModel.metadata.create_all(bind=bind, tables=tables)


def downgrade() -> None:
    bind = op.get_bind()
    SQLModel.metadata.drop_all(bind=bind)
