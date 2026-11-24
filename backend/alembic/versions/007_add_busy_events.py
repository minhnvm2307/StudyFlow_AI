"""Add busy events

Revision ID: 007
"""
revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None

from alembic import op


def upgrade():
    conn = op.get_bind()
    conn.exec_driver_sql("""
CREATE TABLE IF NOT EXISTS busy_events (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    start_at    TIMESTAMPTZ NOT NULL,
    end_at      TIMESTAMPTZ NOT NULL,
    reason      TEXT NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT busy_events_time_order CHECK (end_at > start_at)
)
""")
    conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_busy_events_user_time ON busy_events(user_id, start_at, end_at)")
    conn.exec_driver_sql("""
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'busy_events_updated_at'
    ) THEN
        CREATE TRIGGER busy_events_updated_at BEFORE UPDATE ON busy_events
        FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
    END IF;
END $$;
""")


def downgrade():
    conn = op.get_bind()
    conn.exec_driver_sql("DROP TABLE IF EXISTS busy_events")
