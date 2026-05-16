"""add conversation session and message tables

Revision ID: 20260511_0003
Revises: 20260511_0002
Create Date: 2026-05-11
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "20260511_0003"
down_revision: str | None = "20260511_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS conversation_session (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES app_user(id),
            title VARCHAR(255) NOT NULL DEFAULT '学习画像会话',
            profile_id UUID REFERENCES student_profile(id),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_conversation_session_user_id ON conversation_session(user_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS conversation_message (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id UUID NOT NULL REFERENCES conversation_session(id),
            user_id UUID NOT NULL REFERENCES app_user(id),
            role VARCHAR(32) NOT NULL,
            content TEXT NOT NULL,
            intent VARCHAR(64) DEFAULT 'learning',
            metadata_json JSONB,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_conversation_message_session_id ON conversation_message(session_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS conversation_message CASCADE")
    op.execute("DROP TABLE IF EXISTS conversation_session CASCADE")
