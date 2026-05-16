"""baseline schema aligned with unified technical baseline

Revision ID: 20260430_0001
Revises:
Create Date: 2026-04-30
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from alembic import op


revision: str = "20260430_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    schema_path = Path(__file__).resolve().parents[2] / "app" / "db" / "schema.sql"
    for statement in schema_path.read_text(encoding="utf-8").split(";"):
        sql = statement.strip()
        if sql:
            op.execute(sql)


def downgrade() -> None:
    tables = [
        "audit_log",
        "embedding_index",
        "recommendation_record",
        "learning_record",
        "prompt_template",
        "agent_event_log",
        "agent_task",
        "agent_workflow",
        "learning_path_node",
        "learning_path",
        "answer_record",
        "question",
        "media_asset",
        "resource_version",
        "learning_resource",
        "knowledge_point",
        "chapter",
        "course",
        "learning_goal",
        "student_profile_history",
        "student_profile",
        "app_user",
    ]
    for table in tables:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
