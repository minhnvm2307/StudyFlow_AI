"""Add topic hierarchy and task scope metadata.

Revision ID: 009
Revises: 008
"""
revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None

from alembic import op


def upgrade():
    conn = op.get_bind()
    conn.exec_driver_sql("ALTER TABLE topics ADD COLUMN IF NOT EXISTS parent_topic_id TEXT")
    conn.exec_driver_sql("ALTER TABLE topics ADD COLUMN IF NOT EXISTS parent_topic_title TEXT")
    conn.exec_driver_sql("ALTER TABLE topics ADD COLUMN IF NOT EXISTS is_subtopic BOOLEAN NOT NULL DEFAULT TRUE")
    conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_topics_parent ON topics(subject_id, parent_topic_id)")
    conn.exec_driver_sql("ALTER TABLE study_tasks ADD COLUMN IF NOT EXISTS subtopic_id TEXT")
    conn.exec_driver_sql("ALTER TABLE study_tasks ADD COLUMN IF NOT EXISTS parent_topic_id TEXT")
    conn.exec_driver_sql("ALTER TABLE study_tasks ADD COLUMN IF NOT EXISTS is_partial_topic BOOLEAN NOT NULL DEFAULT FALSE")
    conn.exec_driver_sql("ALTER TABLE study_tasks ADD COLUMN IF NOT EXISTS scope TEXT")
    conn.exec_driver_sql("ALTER TABLE study_tasks ADD COLUMN IF NOT EXISTS earliest_allowed_at TIMESTAMPTZ")


def downgrade():
    conn = op.get_bind()
    conn.exec_driver_sql("ALTER TABLE study_tasks DROP COLUMN IF EXISTS earliest_allowed_at")
    conn.exec_driver_sql("ALTER TABLE study_tasks DROP COLUMN IF EXISTS scope")
    conn.exec_driver_sql("ALTER TABLE study_tasks DROP COLUMN IF EXISTS is_partial_topic")
    conn.exec_driver_sql("ALTER TABLE study_tasks DROP COLUMN IF EXISTS parent_topic_id")
    conn.exec_driver_sql("ALTER TABLE study_tasks DROP COLUMN IF EXISTS subtopic_id")
    conn.exec_driver_sql("DROP INDEX IF EXISTS idx_topics_parent")
    conn.exec_driver_sql("ALTER TABLE topics DROP COLUMN IF EXISTS is_subtopic")
    conn.exec_driver_sql("ALTER TABLE topics DROP COLUMN IF EXISTS parent_topic_title")
    conn.exec_driver_sql("ALTER TABLE topics DROP COLUMN IF EXISTS parent_topic_id")
