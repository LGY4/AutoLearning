"""add profile_event table

Revision ID: 20260517_0006
Revises: 20260515_0005
Create Date: 2026-05-17
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "20260517_0006"
down_revision: str | None = "20260515_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE profile_event (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
            event_type VARCHAR(64) NOT NULL,
            event_payload JSONB NOT NULL,
            confidence NUMERIC(5,2) NOT NULL,
            source_type VARCHAR(64),
            source_id UUID,
            status VARCHAR(32) NOT NULL DEFAULT 'pending',
            applied_at TIMESTAMPTZ,
            error_message TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX ix_profile_event_user_id ON profile_event (user_id)")
    op.execute("CREATE INDEX ix_profile_event_status ON profile_event (status)")
    op.execute("CREATE INDEX ix_profile_event_user_status ON profile_event (user_id, status)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS profile_event")
