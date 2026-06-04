"""add composite indexes and constraints

Revision ID: 20260605_0001
Revises: 20260528_0001
Create Date: 2026-06-05
"""
from alembic import op

revision = "20260605_0001"
down_revision = "20260528_0001"
branch_labels = None
depends_on = None


def upgrade():
    # Composite indexes for frequently queried patterns
    op.execute("CREATE INDEX IF NOT EXISTS ix_student_profile_user_version ON student_profile (user_id, profile_version)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_learning_path_user_updated ON learning_path (user_id, updated_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_profile_event_user_status ON profile_event (user_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_profile_event_user_type ON profile_event (user_id, event_type)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_recommendation_user_completed ON recommendation_record (user_id, completed)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_answer_record_user_question ON answer_record (user_id, question_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_question_status_kp ON question (status, knowledge_point)")

    # Add status index to question table
    op.execute("CREATE INDEX IF NOT EXISTS ix_question_status ON question (status)")

    # Uniqueness constraints
    op.execute("ALTER TABLE resource_version ADD CONSTRAINT uq_resource_version UNIQUE (resource_id, version_no)")
    op.execute("ALTER TABLE learning_path_node ADD CONSTRAINT uq_path_node_order UNIQUE (path_id, node_order)")

    # Fix resource_type column length
    op.execute("ALTER TABLE learning_record ALTER COLUMN resource_type TYPE VARCHAR(64)")


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_student_profile_user_version")
    op.execute("DROP INDEX IF EXISTS ix_learning_path_user_updated")
    op.execute("DROP INDEX IF EXISTS ix_profile_event_user_status")
    op.execute("DROP INDEX IF EXISTS ix_profile_event_user_type")
    op.execute("DROP INDEX IF EXISTS ix_recommendation_user_completed")
    op.execute("DROP INDEX IF EXISTS ix_answer_record_user_question")
    op.execute("DROP INDEX IF EXISTS ix_question_status_kp")
    op.execute("DROP INDEX IF EXISTS ix_question_status")
    op.execute("ALTER TABLE resource_version DROP CONSTRAINT IF EXISTS uq_resource_version")
    op.execute("ALTER TABLE learning_path_node DROP CONSTRAINT IF EXISTS uq_path_node_order")
    op.execute("ALTER TABLE learning_record ALTER COLUMN resource_type TYPE VARCHAR(50)")
