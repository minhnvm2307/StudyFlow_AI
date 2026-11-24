"""Add topic mastery evidence confidence.

Revision ID: 010
Revises: 009
"""
revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None

from alembic import op


def upgrade():
    conn = op.get_bind()
    conn.exec_driver_sql("ALTER TABLE topics ADD COLUMN IF NOT EXISTS mastery_confidence REAL NOT NULL DEFAULT 0")
    conn.exec_driver_sql("ALTER TABLE topics ADD COLUMN IF NOT EXISTS mastery_evidence_source TEXT NOT NULL DEFAULT 'none'")
    conn.exec_driver_sql(
        """UPDATE topics
           SET mastery_confidence=0.9,
               mastery_evidence_source='quiz'
           WHERE mastery_confidence=0
             AND (is_learned=true OR awaiting_diagnostic=false OR fsrs_last_review IS NOT NULL)"""
    )


def downgrade():
    conn = op.get_bind()
    conn.exec_driver_sql("ALTER TABLE topics DROP COLUMN IF EXISTS mastery_evidence_source")
    conn.exec_driver_sql("ALTER TABLE topics DROP COLUMN IF EXISTS mastery_confidence")
