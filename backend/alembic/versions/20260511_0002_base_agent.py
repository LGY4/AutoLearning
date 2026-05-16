"""add base agent storage

Revision ID: 20260511_0002
Revises: 20260430_0001
Create Date: 2026-05-11
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "20260511_0002"
down_revision: str | None = "20260430_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS base_agent (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES app_user(id),
            name VARCHAR(128) NOT NULL,
            description TEXT NOT NULL,
            system_prompt TEXT NOT NULL,
            applies_to JSONB NOT NULL DEFAULT '[]'::jsonb,
            model_provider VARCHAR(64) NOT NULL DEFAULT 'spark',
            output_style VARCHAR(64) NOT NULL DEFAULT 'structured',
            is_system BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_base_agent_user_id ON base_agent(user_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS base_agent CASCADE")
