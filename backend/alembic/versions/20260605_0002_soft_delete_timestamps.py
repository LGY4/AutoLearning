"""soft delete and missing timestamps

Revision ID: 20260605_0002
Revises: 20260605_0001
Create Date: 2026-06-05
"""
from alembic import op
import sqlalchemy as sa

revision = "20260605_0002"
down_revision = "20260605_0001"
branch_labels = None
depends_on = None


def upgrade():
    # Add deleted_at for soft delete
    op.add_column("learning_resource", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("CREATE INDEX IF NOT EXISTS ix_learning_resource_deleted_at ON learning_resource (deleted_at)")

    op.add_column("learning_path", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("CREATE INDEX IF NOT EXISTS ix_learning_path_deleted_at ON learning_path (deleted_at)")

    op.add_column("question", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("CREATE INDEX IF NOT EXISTS ix_question_deleted_at ON question (deleted_at)")

    # Add missing timestamps
    op.add_column("chapter", sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.add_column("chapter", sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()))

    op.add_column("learning_goal", sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()))


def downgrade():
    op.drop_column("learning_resource", "deleted_at")
    op.drop_column("learning_path", "deleted_at")
    op.drop_column("question", "deleted_at")
    op.drop_column("chapter", "created_at")
    op.drop_column("chapter", "updated_at")
    op.drop_column("learning_goal", "updated_at")
