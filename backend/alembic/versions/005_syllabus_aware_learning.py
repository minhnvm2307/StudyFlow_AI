"""Add syllabus-aware learning tables and topic/task gates.

Revision ID: 005
Revises: 004
"""
revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None

from alembic import op


def upgrade():
    conn = op.get_bind()
    conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS course_syllabi (
            id TEXT PRIMARY KEY,
            subject_id TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            source_type TEXT NOT NULL DEFAULT 'manual',
            status TEXT NOT NULL DEFAULT 'ready',
            raw_text TEXT NOT NULL DEFAULT '',
            parsed_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            current_lesson_id TEXT,
            current_week INTEGER,
            join_position TEXT NOT NULL DEFAULT 'beginning',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_course_syllabi_subject ON course_syllabi(subject_id)")
    conn.exec_driver_sql("DROP TRIGGER IF EXISTS course_syllabi_updated_at ON course_syllabi")
    conn.exec_driver_sql("""
        CREATE TRIGGER course_syllabi_updated_at BEFORE UPDATE ON course_syllabi
        FOR EACH ROW EXECUTE FUNCTION touch_updated_at()
    """)
    conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS syllabus_lessons (
            id TEXT PRIMARY KEY,
            syllabus_id TEXT NOT NULL REFERENCES course_syllabi(id) ON DELETE CASCADE,
            subject_id TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
            week_number INTEGER,
            lesson_number INTEGER,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            assigned_readings TEXT[] NOT NULL DEFAULT '{}',
            starts_on DATE,
            ends_on DATE,
            status TEXT NOT NULL DEFAULT 'future',
            order_idx INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_syllabus_lessons_subject ON syllabus_lessons(subject_id, order_idx)")
    conn.exec_driver_sql("DROP TRIGGER IF EXISTS syllabus_lessons_updated_at ON syllabus_lessons")
    conn.exec_driver_sql("""
        CREATE TRIGGER syllabus_lessons_updated_at BEFORE UPDATE ON syllabus_lessons
        FOR EACH ROW EXECUTE FUNCTION touch_updated_at()
    """)
    conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS lesson_material_mappings (
            id TEXT PRIMARY KEY,
            lesson_id TEXT NOT NULL REFERENCES syllabus_lessons(id) ON DELETE CASCADE,
            topic_id TEXT REFERENCES topics(id) ON DELETE CASCADE,
            source_id TEXT REFERENCES course_sources(id) ON DELETE CASCADE,
            chunk_id TEXT REFERENCES document_chunks(id) ON DELETE CASCADE,
            confidence REAL NOT NULL DEFAULT 0,
            reason TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_lesson_mappings_lesson ON lesson_material_mappings(lesson_id)")
    conn.exec_driver_sql("ALTER TABLE topics ADD COLUMN IF NOT EXISTS lesson_id TEXT REFERENCES syllabus_lessons(id) ON DELETE SET NULL")
    conn.exec_driver_sql("ALTER TABLE topics ADD COLUMN IF NOT EXISTS learning_state TEXT NOT NULL DEFAULT 'taught'")
    conn.exec_driver_sql("ALTER TABLE topics ADD COLUMN IF NOT EXISTS practice_allowed BOOLEAN NOT NULL DEFAULT TRUE")
    conn.exec_driver_sql("ALTER TABLE study_tasks ADD COLUMN IF NOT EXISTS lesson_id TEXT REFERENCES syllabus_lessons(id) ON DELETE SET NULL")
    conn.exec_driver_sql("ALTER TABLE study_tasks ADD COLUMN IF NOT EXISTS lesson_title TEXT")
    conn.exec_driver_sql("ALTER TABLE study_tasks ADD COLUMN IF NOT EXISTS learning_state TEXT")


def downgrade():
    conn = op.get_bind()
    conn.exec_driver_sql("ALTER TABLE study_tasks DROP COLUMN IF EXISTS learning_state")
    conn.exec_driver_sql("ALTER TABLE study_tasks DROP COLUMN IF EXISTS lesson_title")
    conn.exec_driver_sql("ALTER TABLE study_tasks DROP COLUMN IF EXISTS lesson_id")
    conn.exec_driver_sql("ALTER TABLE topics DROP COLUMN IF EXISTS practice_allowed")
    conn.exec_driver_sql("ALTER TABLE topics DROP COLUMN IF EXISTS learning_state")
    conn.exec_driver_sql("ALTER TABLE topics DROP COLUMN IF EXISTS lesson_id")
    conn.exec_driver_sql("DROP TABLE IF EXISTS lesson_material_mappings")
    conn.exec_driver_sql("DROP TABLE IF EXISTS syllabus_lessons")
    conn.exec_driver_sql("DROP TABLE IF EXISTS course_syllabi")
