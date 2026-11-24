-- =============================================================
-- StudyFlow AI — PostgreSQL Database Schema (Production v4)
-- =============================================================
-- Thứ tự chạy: Chạy file này 1 lần qua Alembic hoặc psql trực tiếp.
-- Convention: snake_case columns, TEXT primary keys (slug từ email/uuid),
--             camelCase chỉ xuất hiện trong API layer (FastAPI middleware convert).
-- =============================================================

-- -------------------------------------------------------------
-- 0. HELPER TRIGGER — tự cập nhật updated_at
-- -------------------------------------------------------------
CREATE OR REPLACE FUNCTION touch_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;


-- =============================================================
-- 1. USERS
--    Single source of truth cho profile + FSRS personalization.
--    Không lưu urgency_score hay fsrs_interval — tính on-the-fly.
-- =============================================================
CREATE TABLE users (
    -- Identity
    id                    TEXT PRIMARY KEY,          -- slug từ email: "user-minh-example-com"
    username              TEXT NOT NULL UNIQUE,
    email                 TEXT NOT NULL UNIQUE,
    password_hash         TEXT,                      -- NULL = legacy passwordless

    -- Onboarding
    onboarding_step       INTEGER      NOT NULL DEFAULT 0,
    goal_mode             TEXT,                      -- "semester" | "exam_sprint" | NULL

    -- Study config
    daily_goal_minutes    INTEGER      NOT NULL DEFAULT 30,
    study_days            TEXT[]       NOT NULL DEFAULT '{}',  -- ["Mon","Wed","Fri"]
    study_window          JSONB,                     -- {"start":"08:00","end":"22:00"} | NULL
    quiet_hours           JSONB,                     -- {"start":"22:00","end":"07:00"} | NULL

    -- UX
    mascot_tone           TEXT         NOT NULL DEFAULT 'encouraging',
    notifications         JSONB        NOT NULL DEFAULT '{}'::jsonb,
    xp                    INTEGER      NOT NULL DEFAULT 0,
    streak                INTEGER      NOT NULL DEFAULT 0,
    achievements          JSONB        NOT NULL DEFAULT '[]'::jsonb,

    -- FSRS personalization (populated sau >= 1000 reviews bởi FsrsTuningService)
    fsrs_custom_weights   JSONB,                     -- [17 floats] | NULL = dùng default
    fsrs_tuning           JSONB        NOT NULL DEFAULT '{
        "last_run_at": null,
        "last_rmse": null,
        "review_count_at_last_run": 0
    }'::jsonb,

    -- Scheduling state
    plan_dirty            BOOLEAN      NOT NULL DEFAULT FALSE,  -- trigger rebuild khi TRUE

    created_at            TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_username ON users(username);
CREATE TRIGGER users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();


-- =============================================================
-- 2. SUBJECTS
--    Metadata môn học. KHÔNG embed topics/tasks.
--    coverage_warning được set bởi scheduler, reset khi rebuild thành công.
-- =============================================================
CREATE TABLE subjects (
    id                    TEXT PRIMARY KEY,          -- "subject-1781495257"
    user_id               TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    name                  TEXT    NOT NULL,
    mode                  TEXT    NOT NULL DEFAULT 'semester',  -- "semester" | "exam_sprint"
    exam_date             DATE,
    weekly_goal_minutes   INTEGER NOT NULL DEFAULT 0,
    daily_goal_minutes    INTEGER NOT NULL DEFAULT 30,
    days_available        TEXT[]  NOT NULL DEFAULT '{}',        -- ["Mon","Tue","Thu","Sat"]
    availability_windows  JSONB   NOT NULL DEFAULT '[]'::jsonb, -- [{"day":"Mon","start":"09:00","end":"10:00"}]
    is_priority           BOOLEAN NOT NULL DEFAULT FALSE,
    target_score          INTEGER,
    priority              TEXT    NOT NULL DEFAULT 'medium',
    featured              BOOLEAN NOT NULL DEFAULT FALSE,
    shared                BOOLEAN NOT NULL DEFAULT FALSE,

    -- Scheduler output state
    -- NULL = OK | "INFEASIBLE" = 409 trigger WF-12 | "over_budget:N" = warning banner
    coverage_warning      TEXT,

    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_subjects_user_id ON subjects(user_id);
CREATE TRIGGER subjects_updated_at BEFORE UPDATE ON subjects
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();


-- =============================================================
-- 3. TOPICS
--    Nội dung tĩnh theo giáo trình (sinh bởi LLM section split).
--    Chỉ lưu raw state — level/weak/due là computed properties trong Python.
-- =============================================================
CREATE TABLE topics (
    id                    TEXT PRIMARY KEY,          -- "topic-subject-123-1"
    subject_id            TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    user_id               TEXT NOT NULL,             -- denormalized để tối ưu multi-tenant query

    title                 TEXT    NOT NULL,
    description           TEXT    NOT NULL DEFAULT '',
    section_number        INTEGER NOT NULL DEFAULT 0,
    content_chunk         TEXT    NOT NULL DEFAULT '',  -- summary cho LLM quiz gen
    order_idx             INTEGER NOT NULL DEFAULT 0,   -- thứ tự trong giáo trình (precedence CP)

    -- Cost cho CP-SAT solver (phút học dự kiến, dynamic theo mastery)
    -- Công thức: base_cost = 15 + round((1 - mastery) * 15), min=10 max=30
    cost_mins             INTEGER NOT NULL DEFAULT 20,

    -- BKT raw state (nguồn sự thật duy nhất cho mastery)
    mastery               REAL    NOT NULL DEFAULT 0.15,  -- P(L) ∈ [0,1]; *100 khi ra API
    mastery_confidence    REAL    NOT NULL DEFAULT 0,
    mastery_evidence_source TEXT  NOT NULL DEFAULT 'none',
    p_l0                  REAL    NOT NULL DEFAULT 0.15,  -- prior ban đầu, chỉ để debug
    p_t                   REAL    NOT NULL DEFAULT 0.2,
    p_g                   REAL    NOT NULL DEFAULT 0.2,
    p_s                   REAL    NOT NULL DEFAULT 0.1,
    awaiting_diagnostic   BOOLEAN NOT NULL DEFAULT TRUE,

    -- FSRS-6 raw state (dict từ fsrs.Card.to_dict())
    -- Không flatten field — đọc stability/difficulty từ JSONB khi cần
    fsrs_card             JSONB   NOT NULL DEFAULT '{}'::jsonb,

    -- Extracted từ fsrs_card để tạo index urgency query mà không parse JSONB mỗi lần
    fsrs_stability        REAL    NOT NULL DEFAULT 0.0,
    fsrs_difficulty       REAL    NOT NULL DEFAULT 5.0,
    fsrs_last_review      DATE,
    is_learned            BOOLEAN NOT NULL DEFAULT FALSE,
    -- Ngày đến hạn ôn tập (computed từ last_review + stability sau mỗi submit)
    -- Dùng bởi Pha 2 scheduler để filter due_reviews
    fsrs_due_date         DATE,

    -- Edge-case #4 merge metadata
    merged_from           TEXT[]  NOT NULL DEFAULT '{}',

    -- Parent topic grouping; rows remain schedulable subtopics for MVP.
    parent_topic_id       TEXT,
    parent_topic_title    TEXT,
    is_subtopic           BOOLEAN NOT NULL DEFAULT TRUE,

    -- Syllabus-aware learning gate. Syllabus lessons define timeline;
    -- materials still provide detailed content.
    lesson_id             TEXT,
    learning_state        TEXT    NOT NULL DEFAULT 'taught',
    practice_allowed      BOOLEAN NOT NULL DEFAULT TRUE,

    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_topics_subject_id  ON topics(subject_id);
CREATE INDEX idx_topics_user_id     ON topics(user_id);
-- Index cho urgency scoring: ORDER BY mastery ASC, fsrs_stability ASC
CREATE INDEX idx_topics_urgency     ON topics(subject_id, mastery, fsrs_stability);
-- Index cho Pha 2 scheduler: filter due_date nhanh
CREATE INDEX idx_topics_due_date    ON topics(subject_id, fsrs_due_date)
    WHERE fsrs_due_date IS NOT NULL AND awaiting_diagnostic = FALSE;

CREATE TRIGGER topics_updated_at BEFORE UPDATE ON topics
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();


-- =============================================================
-- 4. STUDY_TASKS
--    Output của Hybrid Scheduler (Pha 1 CP-SAT + Pha 2 FSRS fill).
--    Rebuild toàn bộ future tasks khi plan_dirty = TRUE.
-- =============================================================
CREATE TABLE study_tasks (
    id                TEXT PRIMARY KEY,              -- "task-{date}-{topic_id}"
    subject_id        TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    topic_id          TEXT REFERENCES topics(id)   ON DELETE CASCADE,
    user_id           TEXT NOT NULL,

    topic_title       TEXT NOT NULL,
    type              TEXT NOT NULL,  -- "NEW" (CP-SAT) | "REVIEW" (FSRS fill)
                                      -- | "diagnostic" | "after_class"
    duration_minutes  INTEGER NOT NULL,
    reason            TEXT    NOT NULL DEFAULT '',   -- urgency explanation cho frontend
    scheduled_date    DATE    NOT NULL,
    status            TEXT    NOT NULL DEFAULT 'ready',  -- "ready" | "done" | "missed"
    day               TEXT,                          -- "Mon" derive từ scheduled_date

    title             TEXT,
    start_at          TIMESTAMPTZ,
    end_at            TIMESTAMPTZ,
    priority          TEXT    NOT NULL DEFAULT 'medium',

    lesson_id         TEXT,
    lesson_title      TEXT,
    learning_state    TEXT,
    subtopic_id       TEXT,
    parent_topic_id   TEXT,
    is_partial_topic  BOOLEAN NOT NULL DEFAULT FALSE,
    scope             TEXT,
    earliest_allowed_at TIMESTAMPTZ,

    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_tasks_subject_id      ON study_tasks(subject_id);
CREATE INDEX idx_tasks_user_id         ON study_tasks(user_id);
CREATE INDEX idx_tasks_scheduled_date  ON study_tasks(subject_id, scheduled_date, status);
-- Partial index cho "today ready" query — dùng bởi dashboard mỗi request
CREATE INDEX idx_tasks_today_ready     ON study_tasks(user_id, scheduled_date)
    WHERE status = 'ready';

CREATE TRIGGER tasks_updated_at BEFORE UPDATE ON study_tasks
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();


-- =============================================================
-- 4A. BUSY_EVENTS
--    User-owned unavailable time blocks used by the scheduler.
-- =============================================================
CREATE TABLE busy_events (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    start_at    TIMESTAMPTZ NOT NULL,
    end_at      TIMESTAMPTZ NOT NULL,
    reason      TEXT NOT NULL DEFAULT '',
    recurrence_id TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT busy_events_time_order CHECK (end_at > start_at)
);

CREATE INDEX idx_busy_events_user_time ON busy_events(user_id, start_at, end_at);

CREATE TRIGGER busy_events_updated_at BEFORE UPDATE ON busy_events
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();


-- =============================================================
-- 4B. COURSE/RAG/PRACTICE COMPATIBILITY TABLES
--    PostgreSQL-backed replacement for the removed JSON-file MVP backend.
-- =============================================================
CREATE TABLE course_syllabi (
    id                 TEXT PRIMARY KEY,
    subject_id         TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    user_id            TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_type        TEXT NOT NULL DEFAULT 'manual',
    status             TEXT NOT NULL DEFAULT 'ready',
    raw_text           TEXT NOT NULL DEFAULT '',
    parsed_json        JSONB NOT NULL DEFAULT '{}'::jsonb,
    current_lesson_id  TEXT,
    current_week       INTEGER,
    join_position      TEXT NOT NULL DEFAULT 'beginning',
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_course_syllabi_subject ON course_syllabi(subject_id);
CREATE TRIGGER course_syllabi_updated_at BEFORE UPDATE ON course_syllabi
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

CREATE TABLE syllabus_lessons (
    id                 TEXT PRIMARY KEY,
    syllabus_id        TEXT NOT NULL REFERENCES course_syllabi(id) ON DELETE CASCADE,
    subject_id         TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    week_number        INTEGER,
    lesson_number      INTEGER,
    title              TEXT NOT NULL,
    description        TEXT NOT NULL DEFAULT '',
    assigned_readings  TEXT[] NOT NULL DEFAULT '{}',
    starts_on          DATE,
    ends_on            DATE,
    status             TEXT NOT NULL DEFAULT 'future',
    order_idx          INTEGER NOT NULL DEFAULT 0,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_syllabus_lessons_subject ON syllabus_lessons(subject_id, order_idx);
CREATE TRIGGER syllabus_lessons_updated_at BEFORE UPDATE ON syllabus_lessons
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

ALTER TABLE course_syllabi
    ADD CONSTRAINT fk_course_syllabi_current_lesson
    FOREIGN KEY (current_lesson_id) REFERENCES syllabus_lessons(id) ON DELETE SET NULL;
ALTER TABLE topics
    ADD CONSTRAINT fk_topics_lesson
    FOREIGN KEY (lesson_id) REFERENCES syllabus_lessons(id) ON DELETE SET NULL;
ALTER TABLE study_tasks
    ADD CONSTRAINT fk_study_tasks_lesson
    FOREIGN KEY (lesson_id) REFERENCES syllabus_lessons(id) ON DELETE SET NULL;

CREATE TABLE course_sources (
    id             TEXT PRIMARY KEY,
    subject_id     TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    user_id        TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    filename       TEXT NOT NULL,
    original_name  TEXT NOT NULL DEFAULT '',
    file_type      TEXT NOT NULL DEFAULT 'txt',
    mime_type      TEXT NOT NULL DEFAULT 'text/plain',
    status         TEXT NOT NULL DEFAULT 'ready',
    selected       BOOLEAN NOT NULL DEFAULT TRUE,
    topic_count    INTEGER NOT NULL DEFAULT 0,
    url            TEXT,
    text_content   TEXT,
    storage_path   TEXT,
    error_message  TEXT,
    parsed_at      TIMESTAMPTZ,
    uploaded_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_course_sources_subject ON course_sources(subject_id);
CREATE INDEX idx_course_sources_user ON course_sources(user_id);
CREATE TRIGGER course_sources_updated_at BEFORE UPDATE ON course_sources
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

CREATE TABLE document_chunks (
    id               TEXT PRIMARY KEY,
    subject_id       TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    source_id        TEXT NOT NULL REFERENCES course_sources(id) ON DELETE CASCADE,
    user_id          TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    filename         TEXT NOT NULL,
    chunk_index      INTEGER NOT NULL DEFAULT 0,
    text             TEXT NOT NULL,
    normalized_text  TEXT NOT NULL DEFAULT '',
    quote            TEXT NOT NULL DEFAULT '',
    page             INTEGER,
    page_start       INTEGER,
    page_end         INTEGER,
    section_path     TEXT NOT NULL DEFAULT '',
    section_title    TEXT NOT NULL DEFAULT '',
    topic_ids        TEXT[] NOT NULL DEFAULT '{}',
    content_hash     TEXT NOT NULL DEFAULT '',
    token_count      INTEGER NOT NULL DEFAULT 0,
    embedding_status TEXT NOT NULL DEFAULT 'disabled',
    metadata         JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_document_chunks_subject ON document_chunks(subject_id);
CREATE INDEX idx_document_chunks_source ON document_chunks(source_id);
CREATE INDEX idx_document_chunks_page ON document_chunks(subject_id, page_start, page_end);

CREATE TABLE lesson_material_mappings (
    id          TEXT PRIMARY KEY,
    lesson_id   TEXT NOT NULL REFERENCES syllabus_lessons(id) ON DELETE CASCADE,
    topic_id    TEXT REFERENCES topics(id) ON DELETE CASCADE,
    source_id   TEXT REFERENCES course_sources(id) ON DELETE CASCADE,
    chunk_id    TEXT REFERENCES document_chunks(id) ON DELETE CASCADE,
    confidence  REAL NOT NULL DEFAULT 0,
    reason      TEXT NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_lesson_mappings_lesson ON lesson_material_mappings(lesson_id);

CREATE TABLE chat_threads (
    id         TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title      TEXT NOT NULL DEFAULT 'New conversation',
    origin     TEXT NOT NULL DEFAULT 'normal',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_chat_threads_subject ON chat_threads(subject_id, updated_at DESC);
CREATE TRIGGER chat_threads_updated_at BEFORE UPDATE ON chat_threads
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

CREATE TABLE chat_messages (
    id          TEXT PRIMARY KEY,
    thread_id   TEXT NOT NULL REFERENCES chat_threads(id) ON DELETE CASCADE,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    source_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    actions     JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_chat_messages_thread ON chat_messages(thread_id, created_at);

CREATE TABLE practice_quizzes (
    id                  TEXT PRIMARY KEY,
    subject_id          TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    user_id             TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    topic_id            TEXT REFERENCES topics(id) ON DELETE SET NULL,
    title               TEXT NOT NULL,
    difficulty          TEXT NOT NULL DEFAULT 'medium',
    instructions        TEXT NOT NULL DEFAULT '',
    selected_source_ids TEXT[] NOT NULL DEFAULT '{}',
    questions           JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_practice_quizzes_subject ON practice_quizzes(subject_id, created_at DESC);

CREATE TABLE practice_quiz_results (
    id                           TEXT PRIMARY KEY,
    quiz_id                      TEXT NOT NULL REFERENCES practice_quizzes(id) ON DELETE CASCADE,
    subject_id                   TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    user_id                      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    score                        INTEGER NOT NULL DEFAULT 0,
    total                        INTEGER NOT NULL DEFAULT 0,
    accuracy_percent             INTEGER NOT NULL DEFAULT 0,
    average_seconds_per_question INTEGER NOT NULL DEFAULT 45,
    mistakes                     JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at                   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_practice_results_subject ON practice_quiz_results(subject_id, created_at DESC);

CREATE TABLE flashcards (
    id          TEXT PRIMARY KEY,
    subject_id  TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    topic_id    TEXT REFERENCES topics(id) ON DELETE SET NULL,
    front       TEXT NOT NULL,
    back        TEXT NOT NULL,
    explanation TEXT NOT NULL DEFAULT '',
    source_ref  JSONB,
    due_at      TIMESTAMPTZ,
    last_rating TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_flashcards_subject ON flashcards(subject_id, due_at);
CREATE TRIGGER flashcards_updated_at BEFORE UPDATE ON flashcards
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

CREATE TABLE flashcard_sessions (
    id            TEXT PRIMARY KEY,
    subject_id    TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    user_id       TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    flashcard_ids TEXT[] NOT NULL DEFAULT '{}',
    ratings       JSONB NOT NULL DEFAULT '{}'::jsonb,
    status        TEXT NOT NULL DEFAULT 'in_progress',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TRIGGER flashcard_sessions_updated_at BEFORE UPDATE ON flashcard_sessions
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

CREATE TABLE mastery_records (
    id         TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    topic_id   TEXT REFERENCES topics(id) ON DELETE SET NULL,
    value      INTEGER NOT NULL DEFAULT 0,
    reason     TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =============================================================
-- 5. QUIZ_SESSIONS
-- =============================================================
CREATE TABLE quiz_sessions (
    id            TEXT PRIMARY KEY,          -- "session-{uuid}"
    subject_id    TEXT NOT NULL REFERENCES subjects(id)    ON DELETE CASCADE,
    task_id       TEXT NOT NULL REFERENCES study_tasks(id) ON DELETE CASCADE,
    user_id       TEXT NOT NULL,
    is_diagnostic BOOLEAN NOT NULL DEFAULT FALSE,

    -- Điền sau khi submit
    submitted_at  TIMESTAMPTZ,
    correct       INTEGER,
    total         INTEGER,
    xp_earned     INTEGER,
    feedback      TEXT,

    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_sessions_user_id    ON quiz_sessions(user_id);
CREATE INDEX idx_sessions_subject_id ON quiz_sessions(subject_id);
-- Partial index để check "đã hoàn thành ít nhất 1 mock test" trong readiness checklist
CREATE INDEX idx_sessions_submitted  ON quiz_sessions(user_id, submitted_at)
    WHERE submitted_at IS NOT NULL;


-- =============================================================
-- 6. QUIZ_QUESTIONS
--    Sinh on-the-fly bởi LLM, lưu cùng session.
--    Answer (selected_option, is_correct) điền sau submit — không tách bảng riêng.
-- =============================================================
CREATE TABLE quiz_questions (
    id              TEXT PRIMARY KEY,        -- "topic-abc-q1"
    session_id      TEXT NOT NULL REFERENCES quiz_sessions(id) ON DELETE CASCADE,
    topic_id        TEXT NOT NULL REFERENCES topics(id)        ON DELETE CASCADE,
    user_id         TEXT NOT NULL,

    prompt          TEXT   NOT NULL,
    options         TEXT[] NOT NULL,         -- ["Consistency","Availability",...]
    correct_option  TEXT   NOT NULL,
    explanation     TEXT   NOT NULL DEFAULT '',
    source          TEXT   NOT NULL DEFAULT '',

    -- Điền sau submit
    selected_option TEXT,
    is_correct      BOOLEAN,
    reported        BOOLEAN NOT NULL DEFAULT FALSE,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_questions_session_id ON quiz_questions(session_id);
CREATE INDEX idx_questions_topic_id   ON quiz_questions(topic_id);


-- =============================================================
-- 7. SESSION_MASTERY_DELTAS
--    Lookup table cho masteryDelta[] trong SessionResult API response.
-- =============================================================
CREATE TABLE session_mastery_deltas (
    session_id  TEXT NOT NULL REFERENCES quiz_sessions(id) ON DELETE CASCADE,
    topic_id    TEXT NOT NULL,
    delta       INTEGER NOT NULL,            -- mastery change * 100, VD: +12
    PRIMARY KEY (session_id, topic_id)
);


-- =============================================================
-- 8. FSRS_REVIEW_LOGS
--    Append-only audit trail cho FsrsTuningService.
--    Input cho POST /api/fsrs/tuning/run sau khi >= 1000 reviews.
--    KHÔNG có updated_at vì không bao giờ UPDATE/DELETE row này.
-- =============================================================
CREATE TABLE fsrs_review_logs (
    id            TEXT PRIMARY KEY,          -- "log-{uuid}"
    user_id       TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    subject_id    TEXT NOT NULL,             -- denormalized để filter theo môn
    item_id       TEXT NOT NULL,             -- = topic.id

    rating        SMALLINT    NOT NULL,      -- 1=Again 2=Hard 3=Good 4=Easy
    review_date   TIMESTAMPTZ NOT NULL DEFAULT now(),
    elapsed_days  INTEGER     NOT NULL,      -- ngày kể từ lần review trước (0 nếu lần đầu)
    -- fsrs.State TRƯỚC khi update: 0=Learning 1=Review 2=Relearning
    -- Ghi state trước để optimizer_runner dùng đúng giá trị, không suy đoán lại
    review_state  SMALLINT    NOT NULL DEFAULT 0
);

-- Index chính cho FsrsTuningService.extract_and_format_training_data()
CREATE INDEX idx_fsrs_logs_user   ON fsrs_review_logs(user_id, review_date);
CREATE INDEX idx_fsrs_logs_item   ON fsrs_review_logs(user_id, item_id, review_date);
-- BRIN cho time-series range scan (hiệu quả với append-only data)
CREATE INDEX idx_fsrs_logs_brin   ON fsrs_review_logs USING BRIN(review_date);


-- =============================================================
-- 9. VIEWS — hỗ trợ debug và dashboard query
-- =============================================================
CREATE OR REPLACE VIEW v_topic_status AS
SELECT
    t.id,
    t.user_id,
    t.subject_id,
    t.title,
    t.order_idx,
    t.cost_mins,
    ROUND(t.mastery * 100)::INT AS mastery_pct,
    CASE
        WHEN t.mastery >= 0.85 THEN 'mastered'
        WHEN t.mastery >= 0.60 THEN 'good'
        WHEN t.mastery >= 0.30 THEN 'progressing'
        ELSE 'priority'
    END AS level,
    (t.mastery < 0.4)     AS is_weak,
    t.awaiting_diagnostic,
    t.fsrs_stability,
    t.fsrs_difficulty,
    t.fsrs_last_review,
    t.fsrs_due_date,
    (t.fsrs_due_date <= CURRENT_DATE AND NOT t.awaiting_diagnostic) AS is_due_today
FROM topics t;

CREATE OR REPLACE VIEW v_today_tasks AS
SELECT
    st.*,
    t.mastery,
    t.fsrs_stability,
    t.level  -- NOTE: computed trong Python, view này chỉ dùng để debug
FROM study_tasks st
JOIN v_topic_status t ON t.id = st.topic_id
WHERE st.scheduled_date = CURRENT_DATE;
