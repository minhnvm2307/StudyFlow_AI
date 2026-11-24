"""Add missing columns from DB_SCHEMA v4

Revision ID: 002
"""
revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None

from alembic import op


def upgrade():
    conn = op.get_bind()

    # users: add plan_dirty
    conn.exec_driver_sql("""
        ALTER TABLE users ADD COLUMN IF NOT EXISTS plan_dirty BOOLEAN NOT NULL DEFAULT FALSE
    """)

    # subjects: add coverage_warning
    conn.exec_driver_sql("""
        ALTER TABLE subjects ADD COLUMN IF NOT EXISTS coverage_warning TEXT
    """)

    # topics: add order_idx and fsrs_due_date
    conn.exec_driver_sql("""
        ALTER TABLE topics ADD COLUMN IF NOT EXISTS order_idx INTEGER NOT NULL DEFAULT 0
    """)
    conn.exec_driver_sql("""
        ALTER TABLE topics ADD COLUMN IF NOT EXISTS fsrs_due_date DATE
    """)

    # Add partial index for Pha 2 scheduler
    conn.exec_driver_sql("""
        CREATE INDEX IF NOT EXISTS idx_topics_due_date
        ON topics(subject_id, fsrs_due_date)
        WHERE fsrs_due_date IS NOT NULL AND awaiting_diagnostic = FALSE
    """)


def downgrade():
    conn = op.get_bind()
    conn.exec_driver_sql("DROP INDEX IF EXISTS idx_topics_due_date")
    conn.exec_driver_sql("ALTER TABLE topics DROP COLUMN IF EXISTS fsrs_due_date")
    conn.exec_driver_sql("ALTER TABLE topics DROP COLUMN IF EXISTS order_idx")
    conn.exec_driver_sql("ALTER TABLE subjects DROP COLUMN IF EXISTS coverage_warning")
    conn.exec_driver_sql("ALTER TABLE users DROP COLUMN IF EXISTS plan_dirty")
