"""Add mastery_events table

Revision ID: 012
Down Revision: 011
"""
revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None

from alembic import op


def upgrade():
    conn = op.get_bind()
    conn.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS mastery_events (
            id                  TEXT PRIMARY KEY,
            user_id             TEXT NOT NULL,
            subject_id          TEXT NOT NULL,
            topic_id            TEXT NOT NULL,
            source_type         TEXT NOT NULL,
            source_id           TEXT NOT NULL,
            question_format     TEXT,
            is_diagnostic       BOOLEAN DEFAULT false NOT NULL,
            p_l_before          REAL NOT NULL,
            p_t_used            REAL NOT NULL,
            p_g_used            REAL NOT NULL,
            p_s_used            REAL NOT NULL,
            predicted_p_correct REAL NOT NULL,
            actual_correct      BOOLEAN NOT NULL,
            p_l_obs             REAL NOT NULL,
            p_l_after           REAL NOT NULL,
            excluded            BOOLEAN DEFAULT false NOT NULL,
            exclude_reason      TEXT,
            created_at          TIMESTAMPTZ DEFAULT now() NOT NULL
        )
        """
    )
    conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_mastery_events_topic ON mastery_events (topic_id, created_at)")
    conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_mastery_events_user ON mastery_events (user_id, created_at)")
    conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_mastery_events_format ON mastery_events (question_format) WHERE NOT excluded")
    conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_mastery_events_eval ON mastery_events (excluded, created_at)")


def downgrade():
    conn = op.get_bind()
    conn.exec_driver_sql("DROP TABLE IF EXISTS mastery_events CASCADE")
