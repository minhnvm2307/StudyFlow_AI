"""Add subject availability windows

Revision ID: 008
"""
revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None

from alembic import op


def upgrade():
    conn = op.get_bind()
    conn.exec_driver_sql("""
ALTER TABLE subjects
ADD COLUMN IF NOT EXISTS availability_windows JSONB NOT NULL DEFAULT '[]'::jsonb
""")


def downgrade():
    conn = op.get_bind()
    conn.exec_driver_sql("ALTER TABLE subjects DROP COLUMN IF EXISTS availability_windows")
