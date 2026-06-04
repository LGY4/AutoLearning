"""add knowledge_point and resource_type to learning_record

Revision ID: 20260525_0007
Revises: 20260517_0006
Create Date: 2026-05-25
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "20260525_0007"
down_revision: str | None = "20260517_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE learning_record ADD COLUMN IF NOT EXISTS knowledge_point VARCHAR(255)")
    op.execute("ALTER TABLE learning_record ADD COLUMN IF NOT EXISTS resource_type VARCHAR(50)")
    op.execute("ALTER TABLE learning_resource ADD COLUMN IF NOT EXISTS conversation_id UUID REFERENCES conversation_session(id) ON DELETE SET NULL")
    op.execute("CREATE INDEX IF NOT EXISTS ix_learning_resource_conversation_id ON learning_resource(conversation_id)")


def downgrade() -> None:
    op.execute("ALTER TABLE learning_record DROP COLUMN IF EXISTS knowledge_point")
    op.execute("ALTER TABLE learning_record DROP COLUMN IF EXISTS resource_type")
