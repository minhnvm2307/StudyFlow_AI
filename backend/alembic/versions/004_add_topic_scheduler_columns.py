"""Add topic scheduler columns

Revision ID: 004
"""
revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None

from alembic import op


def upgrade():
    conn = op.get_bind()
    conn.exec_driver_sql("""
        ALTER TABLE topics ADD COLUMN IF NOT EXISTS cost_mins INTEGER NOT NULL DEFAULT 20
    """)
    conn.exec_driver_sql("""
        ALTER TABLE topics ADD COLUMN IF NOT EXISTS is_learned BOOLEAN NOT NULL DEFAULT FALSE
    """)


def downgrade():
    conn = op.get_bind()
    conn.exec_driver_sql("ALTER TABLE topics DROP COLUMN IF EXISTS is_learned")
    conn.exec_driver_sql("ALTER TABLE topics DROP COLUMN IF EXISTS cost_mins")
