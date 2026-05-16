"""add indexes to foreign key columns

Revision ID: 20260515_0005
Revises: 20260514_0004
Create Date: 2026-05-15
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "20260515_0005"
down_revision: str | None = "20260514_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_FK_INDEXES = [
    ("learning_goal", "ix_learning_goal_target_course_id", "target_course_id"),
    ("course", "ix_course_created_by", "created_by"),
    ("knowledge_point", "ix_knowledge_point_chapter_id", "chapter_id"),
    ("learning_resource", "ix_learning_resource_knowledge_point_id", "knowledge_point_id"),
    ("learning_path", "ix_learning_path_goal_id", "goal_id"),
    ("learning_path_node", "ix_learning_path_node_knowledge_point_id", "knowledge_point_id"),
    ("learning_path_node", "ix_learning_path_node_resource_id", "resource_id"),
    ("agent_task", "ix_agent_task_user_id", "user_id"),
    ("agent_event_log", "ix_agent_event_log_task_id", "task_id"),
    ("learning_record", "ix_learning_record_path_id", "path_id"),
    ("learning_record", "ix_learning_record_resource_id", "resource_id"),
    ("recommendation_record", "ix_recommendation_record_resource_id", "resource_id"),
    ("recommendation_record", "ix_recommendation_record_path_id", "path_id"),
    ("conversation_session", "ix_conversation_session_profile_id", "profile_id"),
]


def upgrade() -> None:
    for table, index_name, column in _FK_INDEXES:
        op.execute(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table} ({column})")


def downgrade() -> None:
    for table, index_name, column in _FK_INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {index_name}")
