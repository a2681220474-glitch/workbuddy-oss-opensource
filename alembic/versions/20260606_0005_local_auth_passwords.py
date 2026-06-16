"""Add local auth password storage.

Revision ID: 20260606_0005
Revises: 20260605_0004
Create Date: 2026-06-06
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260606_0005"
down_revision = "20260605_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("local_users")}
    if "password_hash" not in columns:
        op.add_column("local_users", sa.Column("password_hash", sa.String(length=500), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("local_users")}
    if "password_hash" in columns:
        op.drop_column("local_users", "password_hash")
