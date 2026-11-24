"""Unify course/RAG data into PostgreSQL

Revision ID: 003
"""
revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None

from alembic import op


def upgrade():
    conn = op.get_bind()

    conn.exec_driver_sql("""
        ALTER TABLE subjects ADD COLUMN IF NOT EXISTS target_score INTEGER
    """)
    conn.exec_driver_sql("""
        ALTER TABLE subjects ADD COLUMN IF NOT EXISTS priority TEXT NOT NULL DEFAULT 'medium'
    """)
    conn.exec_driver_sql("""
        ALTER TABLE subjects ADD COLUMN IF NOT EXISTS featured BOOLEAN NOT NULL DEFAULT FALSE
    """)
    conn.exec_driver_sql("""
        ALTER TABLE subjects ADD COLUMN IF NOT EXISTS shared BOOLEAN NOT NULL DEFAULT FALSE
    """)

    conn.exec_driver_sql("""
        ALTER TABLE study_tasks ALTER COLUMN topic_id DROP NOT NULL
    """)
    conn.exec_driver_sql("""
        ALTER TABLE study_tasks ADD COLUMN IF NOT EXISTS title TEXT
    """)
    conn.exec_driver_sql("""
        ALTER TABLE study_tasks ADD COLUMN IF NOT EXISTS start_at TIMESTAMPTZ
    """)
    conn.exec_driver_sql("""
        ALTER TABLE study_tasks ADD COLUMN IF NOT EXISTS end_at TIMESTAMPTZ
    """)
    conn.exec_driver_sql("""
        ALTER TABLE study_tasks ADD COLUMN IF NOT EXISTS priority TEXT NOT NULL DEFAULT 'medium'
    """)

    conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS course_sources (
            id TEXT PRIMARY KEY,
            subject_id TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            filename TEXT NOT NULL,
            original_name TEXT NOT NULL DEFAULT '',
            file_type TEXT NOT NULL DEFAULT 'txt',
            mime_type TEXT NOT NULL DEFAULT 'text/plain',
            status TEXT NOT NULL DEFAULT 'ready',
            selected BOOLEAN NOT NULL DEFAULT TRUE,
            topic_count INTEGER NOT NULL DEFAULT 0,
            url TEXT,
            text_content TEXT,
            storage_path TEXT,
            error_message TEXT,
            parsed_at TIMESTAMPTZ,
            uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_course_sources_subject ON course_sources(subject_id)")
    conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_course_sources_user ON course_sources(user_id)")
    conn.exec_driver_sql("""
        DROP TRIGGER IF EXISTS course_sources_updated_at ON course_sources;
        CREATE TRIGGER course_sources_updated_at BEFORE UPDATE ON course_sources
            FOR EACH ROW EXECUTE FUNCTION touch_updated_at()
    """)

    conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS document_chunks (
            id TEXT PRIMARY KEY,
            subject_id TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
            source_id TEXT NOT NULL REFERENCES course_sources(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            filename TEXT NOT NULL,
            chunk_index INTEGER NOT NULL DEFAULT 0,
            text TEXT NOT NULL,
            normalized_text TEXT NOT NULL DEFAULT '',
            quote TEXT NOT NULL DEFAULT '',
            page INTEGER,
            page_start INTEGER,
            page_end INTEGER,
            section_path TEXT NOT NULL DEFAULT '',
            section_title TEXT NOT NULL DEFAULT '',
            topic_ids TEXT[] NOT NULL DEFAULT '{}',
            content_hash TEXT NOT NULL DEFAULT '',
            token_count INTEGER NOT NULL DEFAULT 0,
            embedding_status TEXT NOT NULL DEFAULT 'disabled',
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_document_chunks_subject ON document_chunks(subject_id)")
    conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_document_chunks_source ON document_chunks(source_id)")
    conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_document_chunks_page ON document_chunks(subject_id, page_start, page_end)")

    conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS chat_threads (
            id TEXT PRIMARY KEY,
            subject_id TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title TEXT NOT NULL DEFAULT 'New conversation',
            origin TEXT NOT NULL DEFAULT 'normal',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_chat_threads_subject ON chat_threads(subject_id, updated_at DESC)")
    conn.exec_driver_sql("""
        DROP TRIGGER IF EXISTS chat_threads_updated_at ON chat_threads;
        CREATE TRIGGER chat_threads_updated_at BEFORE UPDATE ON chat_threads
            FOR EACH ROW EXECUTE FUNCTION touch_updated_at()
    """)

    conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id TEXT PRIMARY KEY,
            thread_id TEXT NOT NULL REFERENCES chat_threads(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            source_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
            actions JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_chat_messages_thread ON chat_messages(thread_id, created_at)")

    conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS practice_quizzes (
            id TEXT PRIMARY KEY,
            subject_id TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            topic_id TEXT REFERENCES topics(id) ON DELETE SET NULL,
            title TEXT NOT NULL,
            difficulty TEXT NOT NULL DEFAULT 'medium',
            instructions TEXT NOT NULL DEFAULT '',
            selected_source_ids TEXT[] NOT NULL DEFAULT '{}',
            questions JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_practice_quizzes_subject ON practice_quizzes(subject_id, created_at DESC)")

    conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS practice_quiz_results (
            id TEXT PRIMARY KEY,
            quiz_id TEXT NOT NULL REFERENCES practice_quizzes(id) ON DELETE CASCADE,
            subject_id TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            score INTEGER NOT NULL DEFAULT 0,
            total INTEGER NOT NULL DEFAULT 0,
            accuracy_percent INTEGER NOT NULL DEFAULT 0,
            average_seconds_per_question INTEGER NOT NULL DEFAULT 45,
            mistakes JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_practice_results_subject ON practice_quiz_results(subject_id, created_at DESC)")

    conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS flashcards (
            id TEXT PRIMARY KEY,
            subject_id TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            topic_id TEXT REFERENCES topics(id) ON DELETE SET NULL,
            front TEXT NOT NULL,
            back TEXT NOT NULL,
            explanation TEXT NOT NULL DEFAULT '',
            source_ref JSONB,
            due_at TIMESTAMPTZ,
            last_rating TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_flashcards_subject ON flashcards(subject_id, due_at)")
    conn.exec_driver_sql("""
        DROP TRIGGER IF EXISTS flashcards_updated_at ON flashcards;
        CREATE TRIGGER flashcards_updated_at BEFORE UPDATE ON flashcards
            FOR EACH ROW EXECUTE FUNCTION touch_updated_at()
    """)

    conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS flashcard_sessions (
            id TEXT PRIMARY KEY,
            subject_id TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            flashcard_ids TEXT[] NOT NULL DEFAULT '{}',
            ratings JSONB NOT NULL DEFAULT '{}'::jsonb,
            status TEXT NOT NULL DEFAULT 'in_progress',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    conn.exec_driver_sql("""
        DROP TRIGGER IF EXISTS flashcard_sessions_updated_at ON flashcard_sessions;
        CREATE TRIGGER flashcard_sessions_updated_at BEFORE UPDATE ON flashcard_sessions
            FOR EACH ROW EXECUTE FUNCTION touch_updated_at()
    """)

    conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS mastery_records (
            id TEXT PRIMARY KEY,
            subject_id TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            topic_id TEXT REFERENCES topics(id) ON DELETE SET NULL,
            value INTEGER NOT NULL DEFAULT 0,
            reason TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)


def downgrade():
    conn = op.get_bind()
    conn.exec_driver_sql("DROP TABLE IF EXISTS mastery_records CASCADE")
    conn.exec_driver_sql("DROP TABLE IF EXISTS flashcard_sessions CASCADE")
    conn.exec_driver_sql("DROP TABLE IF EXISTS flashcards CASCADE")
    conn.exec_driver_sql("DROP TABLE IF EXISTS practice_quiz_results CASCADE")
    conn.exec_driver_sql("DROP TABLE IF EXISTS practice_quizzes CASCADE")
    conn.exec_driver_sql("DROP TABLE IF EXISTS chat_messages CASCADE")
    conn.exec_driver_sql("DROP TABLE IF EXISTS chat_threads CASCADE")
    conn.exec_driver_sql("DROP TABLE IF EXISTS document_chunks CASCADE")
    conn.exec_driver_sql("DROP TABLE IF EXISTS course_sources CASCADE")
    conn.exec_driver_sql("ALTER TABLE study_tasks DROP COLUMN IF EXISTS priority")
    conn.exec_driver_sql("ALTER TABLE study_tasks DROP COLUMN IF EXISTS end_at")
    conn.exec_driver_sql("ALTER TABLE study_tasks DROP COLUMN IF EXISTS start_at")
    conn.exec_driver_sql("ALTER TABLE study_tasks DROP COLUMN IF EXISTS title")
    conn.exec_driver_sql("ALTER TABLE subjects DROP COLUMN IF EXISTS shared")
    conn.exec_driver_sql("ALTER TABLE subjects DROP COLUMN IF EXISTS featured")
    conn.exec_driver_sql("ALTER TABLE subjects DROP COLUMN IF EXISTS priority")
    conn.exec_driver_sql("ALTER TABLE subjects DROP COLUMN IF EXISTS target_score")
