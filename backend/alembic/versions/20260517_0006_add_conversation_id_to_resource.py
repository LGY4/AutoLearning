"""add conversation_id to learning_resource

Revision ID: 20260517_0006
Revises: 20260515_0005
Create Date: 2026-05-17
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260517_0006"
down_revision: str | None = "20260515_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE learning_resource ADD COLUMN IF NOT EXISTS conversation_id UUID "
        "REFERENCES conversation_session(id) ON DELETE SET NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_learning_resource_conversation_id "
        "ON learning_resource(conversation_id)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE learning_resource DROP COLUMN IF EXISTS conversation_id")
