"""Initial schema

Revision ID: 001
"""
revision = "001"
down_revision = None
branch_labels = None
depends_on = None

from alembic import op


def upgrade():
    conn = op.get_bind()

    conn.exec_driver_sql("""
CREATE OR REPLACE FUNCTION touch_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$
""")

    conn.exec_driver_sql("""
CREATE TABLE users (
    id                  TEXT PRIMARY KEY,
    email               TEXT NOT NULL UNIQUE,
    password_hash       TEXT,
    onboarding_step     INTEGER     NOT NULL DEFAULT 0,
    goal_mode           TEXT,
    daily_goal_minutes  INTEGER     NOT NULL DEFAULT 30,
    study_days          TEXT[]      NOT NULL DEFAULT '{}',
    study_window        JSONB,
    quiet_hours         JSONB,
    mascot_tone         TEXT        NOT NULL DEFAULT 'encouraging',
    notifications       JSONB       NOT NULL DEFAULT '{}',
    xp                  INTEGER     NOT NULL DEFAULT 0,
    streak              INTEGER     NOT NULL DEFAULT 0,
    fsrs_custom_weights JSONB,
    fsrs_tuning         JSONB       NOT NULL DEFAULT '{"last_run_at":null,"last_rmse":null,"review_count_at_last_run":0}',
    achievements        JSONB       NOT NULL DEFAULT '[]',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
)
""")
    conn.exec_driver_sql("CREATE INDEX idx_users_email ON users(email)")
    conn.exec_driver_sql("""
CREATE TRIGGER users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at()
""")

    conn.exec_driver_sql("""
CREATE TABLE subjects (
    id                  TEXT PRIMARY KEY,
    user_id             TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name                TEXT NOT NULL,
    mode                TEXT NOT NULL DEFAULT 'semester',
    exam_date           DATE,
    weekly_goal_minutes INTEGER NOT NULL DEFAULT 0,
    daily_goal_minutes  INTEGER NOT NULL DEFAULT 30,
    days_available      TEXT[]  NOT NULL DEFAULT '{}',
    is_priority         BOOLEAN NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
)
""")
    conn.exec_driver_sql("CREATE INDEX idx_subjects_user_id ON subjects(user_id)")
    conn.exec_driver_sql("""
CREATE TRIGGER subjects_updated_at BEFORE UPDATE ON subjects
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at()
""")

    conn.exec_driver_sql("""
CREATE TABLE topics (
    id                  TEXT PRIMARY KEY,
    subject_id          TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    user_id             TEXT NOT NULL,
    title               TEXT NOT NULL,
    description         TEXT NOT NULL DEFAULT '',
    section_number      INTEGER NOT NULL DEFAULT 0,
    content_chunk       TEXT NOT NULL DEFAULT '',
    mastery             REAL    NOT NULL DEFAULT 0.15,
    mastery_confidence  REAL    NOT NULL DEFAULT 0,
    mastery_evidence_source TEXT NOT NULL DEFAULT 'none',
    p_l0                REAL    NOT NULL DEFAULT 0.15,
    p_t                 REAL    NOT NULL DEFAULT 0.2,
    p_g                 REAL    NOT NULL DEFAULT 0.2,
    p_s                 REAL    NOT NULL DEFAULT 0.1,
    awaiting_diagnostic BOOLEAN NOT NULL DEFAULT TRUE,
    fsrs_card           JSONB   NOT NULL DEFAULT '{}',
    fsrs_stability      REAL    NOT NULL DEFAULT 0.0,
    fsrs_difficulty     REAL    NOT NULL DEFAULT 5.0,
    fsrs_last_review    DATE,
    merged_from         TEXT[]  NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
)
""")
    conn.exec_driver_sql("CREATE INDEX idx_topics_subject_id ON topics(subject_id)")
    conn.exec_driver_sql("CREATE INDEX idx_topics_user_id    ON topics(user_id)")
    conn.exec_driver_sql("CREATE INDEX idx_topics_urgency    ON topics(subject_id, mastery, fsrs_stability)")
    conn.exec_driver_sql("""
CREATE TRIGGER topics_updated_at BEFORE UPDATE ON topics
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at()
""")

    conn.exec_driver_sql("""
CREATE TABLE study_tasks (
    id               TEXT PRIMARY KEY,
    subject_id       TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    topic_id         TEXT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    user_id          TEXT NOT NULL,
    topic_title      TEXT NOT NULL,
    type             TEXT NOT NULL,
    duration_minutes INTEGER NOT NULL,
    reason           TEXT NOT NULL DEFAULT '',
    scheduled_date   DATE NOT NULL,
    status           TEXT NOT NULL DEFAULT 'ready',
    day              TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
)
""")
    conn.exec_driver_sql("CREATE INDEX idx_tasks_subject_id     ON study_tasks(subject_id)")
    conn.exec_driver_sql("CREATE INDEX idx_tasks_user_id        ON study_tasks(user_id)")
    conn.exec_driver_sql("CREATE INDEX idx_tasks_scheduled_date ON study_tasks(subject_id, scheduled_date, status)")
    conn.exec_driver_sql("CREATE INDEX idx_tasks_today_ready    ON study_tasks(user_id, scheduled_date, status) WHERE status = 'ready'")
    conn.exec_driver_sql("""
CREATE TRIGGER tasks_updated_at BEFORE UPDATE ON study_tasks
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at()
""")

    conn.exec_driver_sql("""
CREATE TABLE quiz_sessions (
    id            TEXT PRIMARY KEY,
    subject_id    TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    task_id       TEXT NOT NULL REFERENCES study_tasks(id) ON DELETE CASCADE,
    user_id       TEXT NOT NULL,
    is_diagnostic BOOLEAN NOT NULL DEFAULT FALSE,
    submitted_at  TIMESTAMPTZ,
    correct       INTEGER,
    total         INTEGER,
    xp_earned     INTEGER,
    feedback      TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
)
""")
    conn.exec_driver_sql("CREATE INDEX idx_sessions_user_id    ON quiz_sessions(user_id)")
    conn.exec_driver_sql("CREATE INDEX idx_sessions_subject_id ON quiz_sessions(subject_id)")
    conn.exec_driver_sql("CREATE INDEX idx_sessions_submitted  ON quiz_sessions(user_id, submitted_at) WHERE submitted_at IS NOT NULL")

    conn.exec_driver_sql("""
CREATE TABLE quiz_questions (
    id              TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL REFERENCES quiz_sessions(id) ON DELETE CASCADE,
    topic_id        TEXT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    user_id         TEXT NOT NULL,
    prompt          TEXT NOT NULL,
    options         TEXT[]  NOT NULL,
    correct_option  TEXT    NOT NULL,
    explanation     TEXT    NOT NULL DEFAULT '',
    source          TEXT    NOT NULL DEFAULT '',
    selected_option TEXT,
    is_correct      BOOLEAN,
    reported        BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
)
""")
    conn.exec_driver_sql("CREATE INDEX idx_questions_session_id ON quiz_questions(session_id)")
    conn.exec_driver_sql("CREATE INDEX idx_questions_topic_id   ON quiz_questions(topic_id)")

    conn.exec_driver_sql("""
CREATE TABLE fsrs_review_logs (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    subject_id   TEXT NOT NULL,
    item_id      TEXT NOT NULL,
    rating       SMALLINT NOT NULL,
    review_date  TIMESTAMPTZ NOT NULL DEFAULT now(),
    elapsed_days INTEGER NOT NULL,
    review_state SMALLINT NOT NULL DEFAULT 0
)
""")
    conn.exec_driver_sql("CREATE INDEX idx_fsrs_logs_user ON fsrs_review_logs(user_id, review_date)")
    conn.exec_driver_sql("CREATE INDEX idx_fsrs_logs_item ON fsrs_review_logs(user_id, item_id, review_date)")
    conn.exec_driver_sql("CREATE INDEX idx_fsrs_logs_brin ON fsrs_review_logs USING BRIN(review_date)")

    conn.exec_driver_sql("""
CREATE TABLE session_mastery_deltas (
    session_id TEXT NOT NULL REFERENCES quiz_sessions(id) ON DELETE CASCADE,
    topic_id   TEXT NOT NULL,
    delta      INTEGER NOT NULL,
    PRIMARY KEY (session_id, topic_id)
)
""")

    conn.exec_driver_sql("""
CREATE VIEW v_topic_status AS
SELECT
    t.id, t.user_id, t.subject_id, t.title,
    ROUND(t.mastery * 100) AS mastery_pct,
    CASE
        WHEN t.mastery >= 0.85 THEN 'mastered'
        WHEN t.mastery >= 0.60 THEN 'good'
        WHEN t.mastery >= 0.30 THEN 'progressing'
        ELSE 'priority'
    END AS level,
    t.mastery < 0.4 AS is_weak,
    t.awaiting_diagnostic, t.fsrs_stability, t.fsrs_difficulty, t.fsrs_last_review
FROM topics t
""")

    conn.exec_driver_sql("""
CREATE VIEW v_today_tasks AS
SELECT st.*, t.title AS topic_title_current, t.mastery
FROM study_tasks st
JOIN topics t ON t.id = st.topic_id
WHERE st.scheduled_date = CURRENT_DATE
""")


def downgrade():
    conn = op.get_bind()
    conn.exec_driver_sql("DROP VIEW IF EXISTS v_today_tasks, v_topic_status CASCADE")
    conn.exec_driver_sql("DROP TABLE IF EXISTS session_mastery_deltas, fsrs_review_logs, quiz_questions, quiz_sessions, study_tasks, topics, subjects, users CASCADE")
    conn.exec_driver_sql("DROP FUNCTION IF EXISTS touch_updated_at CASCADE")
