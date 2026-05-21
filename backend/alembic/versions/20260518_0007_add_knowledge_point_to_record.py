"""add knowledge_point to learning_record

Revision ID: 20260518_0007
Revises: 20260517_0006
Create Date: 2026-05-18
"""
from alembic import op

revision = "20260518_0007"
down_revision = "20260517_0006"

def upgrade():
    op.execute("ALTER TABLE learning_record ADD COLUMN IF NOT EXISTS knowledge_point VARCHAR(255)")
    op.execute("ALTER TABLE learning_record ADD COLUMN IF NOT EXISTS path_id UUID")
    op.execute("ALTER TABLE learning_record ADD COLUMN IF NOT EXISTS resource_id UUID")
    op.execute("ALTER TABLE learning_record ADD COLUMN IF NOT EXISTS resource_type VARCHAR(50)")

def downgrade():
    op.execute("ALTER TABLE learning_record DROP COLUMN IF EXISTS resource_type")
    op.execute("ALTER TABLE learning_record DROP COLUMN IF EXISTS knowledge_point")
    op.execute("ALTER TABLE learning_record DROP COLUMN IF EXISTS path_id")
    op.execute("ALTER TABLE learning_record DROP COLUMN IF EXISTS resource_id")
