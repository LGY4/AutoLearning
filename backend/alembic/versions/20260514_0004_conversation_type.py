"""add conversation_type column

Revision ID: 20260514_0004
Revises: 20260511_0003
Create Date: 2026-05-14
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "20260514_0004"
down_revision: str | None = "20260511_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE conversation_session ADD COLUMN IF NOT EXISTS conversation_type VARCHAR(32) NOT NULL DEFAULT 'learning'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE conversation_session DROP COLUMN IF EXISTS conversation_type")
