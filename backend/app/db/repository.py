"""All DB queries — raw asyncpg, no ORM. All functions are async def."""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from typing import Any

import asyncpg

from app.schemas.fsrs import FsrsReviewLog
from app.schemas.profile import FsrsTuningState, UserProfile
from app.schemas.session import QuizQuestion, QuizSession
from app.schemas.subject import Subject
from app.schemas.task import StudyTask
from app.schemas.topic import Topic


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _j(val, default=None):
    """Safely parse JSONB values, including rows accidentally stored as JSON strings."""
    if val is None:
        return default
    parsed = val
    for _ in range(3):
        if not isinstance(parsed, str):
            return parsed
        try:
            parsed = json.loads(parsed)
        except Exception:
            return default
    return parsed

def _row_get(row: asyncpg.Record, key: str, default=None):
    try:
        return row[key]
    except (KeyError, IndexError):
        return default


def _row_to_profile(row: asyncpg.Record) -> UserProfile:
    fsrs_tuning_raw = _j(row["fsrs_tuning"], {})
    return UserProfile(
        id=row["id"],
        username=_row_get(row, "username"),
        email=row["email"],
        onboarding_step=row["onboarding_step"],
        goal_mode=row["goal_mode"],
        daily_goal_minutes=row["daily_goal_minutes"],
        study_days=list(row["study_days"] or []),
        study_window=_j(row["study_window"]),
        quiet_hours=_j(row["quiet_hours"]),
        mascot_tone=row["mascot_tone"],
        notifications=_j(row["notifications"], {}),
        xp=row["xp"],
        streak=row["streak"],
        fsrs_custom_weights=_j(row["fsrs_custom_weights"]),
        fsrs_tuning=FsrsTuningState(**fsrs_tuning_raw),
        plan_dirty=row["plan_dirty"],
    )


def _row_to_subject(row: asyncpg.Record) -> Subject:
    return Subject(
        id=row["id"],
        user_id=row["user_id"],
        name=row["name"],
        mode=row["mode"],
        exam_date=row["exam_date"],
        weekly_goal_minutes=row["weekly_goal_minutes"],
        daily_goal_minutes=row["daily_goal_minutes"],
        days_available=list(row["days_available"] or []),
        availability_windows=_j(_row_get(row, "availability_windows"), []),
        is_priority=row["is_priority"],
        coverage_warning=row["coverage_warning"],
    )


def _row_to_topic(row: asyncpg.Record) -> Topic:
    fsrs_card = _j(row["fsrs_card"], {})
    return Topic(
        id=row["id"],
        subject_id=row["subject_id"],
        user_id=row["user_id"],
        title=row["title"],
        description=row["description"] or "",
        section_number=row["section_number"],
        content_chunk=row["content_chunk"] or "",
        order_idx=row["order_idx"],
        cost_mins=row["cost_mins"],
        mastery=row["mastery"],
        p_l0=row["p_l0"],
        p_t=row["p_t"],
        p_g=row["p_g"],
        p_s=row["p_s"],
        awaiting_diagnostic=row["awaiting_diagnostic"],
        mastery_confidence=float(_row_get(row, "mastery_confidence", 0.0) or 0.0),
        mastery_evidence_source=_row_get(row, "mastery_evidence_source", "none") or "none",
        fsrs_card=fsrs_card,
        fsrs_stability=row["fsrs_stability"],
        fsrs_difficulty=row["fsrs_difficulty"],
        fsrs_last_review=row["fsrs_last_review"],
        fsrs_due_date=row["fsrs_due_date"],
        merged_from=list(row["merged_from"] or []),
        is_learned=row["is_learned"],
        parent_topic_id=_row_get(row, "parent_topic_id"),
        parent_topic_title=_row_get(row, "parent_topic_title"),
        is_subtopic=bool(_row_get(row, "is_subtopic", True)),
        lesson_id=_row_get(row, "lesson_id"),
        learning_state=_row_get(row, "learning_state", "taught") or "taught",
        practice_allowed=bool(_row_get(row, "practice_allowed", True)),
        lesson_starts_on=_row_get(row, "lesson_starts_on"),
        lesson_ends_on=_row_get(row, "lesson_ends_on"),
    )


def _row_to_task(row: asyncpg.Record) -> StudyTask:
    return StudyTask(
        id=row["id"],
        subject_id=row["subject_id"],
        topic_id=row["topic_id"],
        user_id=row["user_id"],
        topic_title=row["topic_title"],
        type=row["type"],
        duration_minutes=row["duration_minutes"],
        reason=row["reason"] or "",
        scheduled_date=row["scheduled_date"],
        status=row["status"],
        day=row["day"],
        title=_row_get(row, "title"),
        start_at=_row_get(row, "start_at"),
        end_at=_row_get(row, "end_at"),
        priority=_row_get(row, "priority", "medium") or "medium",
        lesson_id=_row_get(row, "lesson_id"),
        lesson_title=_row_get(row, "lesson_title"),
        learning_state=_row_get(row, "learning_state"),
        subtopic_id=_row_get(row, "subtopic_id"),
        parent_topic_id=_row_get(row, "parent_topic_id"),
        is_partial_topic=bool(_row_get(row, "is_partial_topic", False)),
        scope=_row_get(row, "scope"),
        earliest_allowed_at=_row_get(row, "earliest_allowed_at"),
    )


def _row_to_session(row: asyncpg.Record) -> QuizSession:
    return QuizSession(
        id=row["id"],
        subject_id=row["subject_id"],
        task_id=row["task_id"],
        user_id=row["user_id"],
        is_diagnostic=row["is_diagnostic"],
        submitted_at=row["submitted_at"].isoformat() if row["submitted_at"] else None,
        correct=row["correct"],
        total=row["total"],
        xp_earned=row["xp_earned"],
        feedback=row["feedback"],
    )


def _row_to_question(row: asyncpg.Record) -> QuizQuestion:
    return QuizQuestion(
        id=row["id"],
        session_id=row["session_id"],
        topic_id=row["topic_id"],
        user_id=row["user_id"],
        prompt=row["prompt"],
        options=list(row["options"] or []),
        correct_option=row["correct_option"],
        explanation=row["explanation"] or "",
        source=row["source"] or "",
        selected_option=row["selected_option"],
        is_correct=row["is_correct"],
        reported=row["reported"],
    )


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

async def get_profile(pool: asyncpg.Pool, user_id: str) -> UserProfile | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
    return _row_to_profile(row) if row else None


async def update_profile(pool: asyncpg.Pool, user_id: str, **fields) -> UserProfile | None:
    if not fields:
        return await get_profile(pool, user_id)
    sets, vals = [], [user_id]
    for k, v in fields.items():
        vals.append(v)
        sets.append(f"{k} = ${len(vals)}")
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"UPDATE users SET {', '.join(sets)} WHERE id = $1 RETURNING *", *vals
        )
    return _row_to_profile(row) if row else None



async def set_plan_dirty(pool: asyncpg.Pool, user_id: str, dirty: bool) -> None:
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET plan_dirty = $2 WHERE id = $1", user_id, dirty)


async def is_plan_dirty(pool: asyncpg.Pool, user_id: str) -> bool:
    async with pool.acquire() as conn:
        val = await conn.fetchval("SELECT plan_dirty FROM users WHERE id = $1", user_id)
    return bool(val)


# ---------------------------------------------------------------------------
# Subjects
# ---------------------------------------------------------------------------

async def get_subject(pool: asyncpg.Pool, subject_id: str) -> Subject | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM subjects WHERE id = $1", subject_id)
    return _row_to_subject(row) if row else None


async def get_subjects(pool: asyncpg.Pool, user_id: str) -> dict[str, Subject]:
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM subjects WHERE user_id = $1", user_id)
    return {r["id"]: _row_to_subject(r) for r in rows}


async def save_subject(pool: asyncpg.Pool, subject: Subject) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO subjects (id, user_id, name, mode, exam_date, weekly_goal_minutes,
               daily_goal_minutes, days_available, availability_windows, is_priority, coverage_warning)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
               ON CONFLICT (id) DO UPDATE SET
                 name=EXCLUDED.name, mode=EXCLUDED.mode, exam_date=EXCLUDED.exam_date,
                 weekly_goal_minutes=EXCLUDED.weekly_goal_minutes,
                 daily_goal_minutes=EXCLUDED.daily_goal_minutes,
                 days_available=EXCLUDED.days_available,
                 availability_windows=EXCLUDED.availability_windows,
                 is_priority=EXCLUDED.is_priority,
                 coverage_warning=EXCLUDED.coverage_warning""",
            subject.id, subject.user_id, subject.name, subject.mode,
            subject.exam_date, subject.weekly_goal_minutes, subject.daily_goal_minutes,
            subject.days_available, subject.availability_windows,
            subject.is_priority, subject.coverage_warning,
        )


async def update_subject(pool: asyncpg.Pool, subject_id: str, **fields) -> None:
    if not fields:
        return
    sets, vals = [], [subject_id]
    for k, v in fields.items():
        vals.append(v)
        sets.append(f"{k} = ${len(vals)}")
    async with pool.acquire() as conn:
        await conn.execute(f"UPDATE subjects SET {', '.join(sets)} WHERE id = $1", *vals)


# ---------------------------------------------------------------------------
# Topics
# ---------------------------------------------------------------------------

async def get_topics(pool: asyncpg.Pool, subject_id: str) -> list[Topic]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT t.*, sl.starts_on AS lesson_starts_on, sl.ends_on AS lesson_ends_on
               FROM topics t
               LEFT JOIN syllabus_lessons sl ON sl.id=t.lesson_id
               WHERE t.subject_id = $1
               ORDER BY t.order_idx""",
            subject_id,
        )
    return [_row_to_topic(r) for r in rows]


async def get_topic(pool: asyncpg.Pool, topic_id: str) -> Topic | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT t.*, sl.starts_on AS lesson_starts_on, sl.ends_on AS lesson_ends_on
               FROM topics t
               LEFT JOIN syllabus_lessons sl ON sl.id=t.lesson_id
               WHERE t.id = $1""",
            topic_id,
        )
    return _row_to_topic(row) if row else None


async def save_topics(pool: asyncpg.Pool, topics: list[Topic]) -> None:
    async with pool.acquire() as conn:
        for t in topics:
            await conn.execute(
                """INSERT INTO topics (id, subject_id, user_id, title, description, section_number,
                   content_chunk, order_idx, cost_mins, mastery, p_l0, p_t, p_g, p_s,
                   awaiting_diagnostic, fsrs_card, fsrs_stability, fsrs_difficulty,
                   fsrs_last_review, fsrs_due_date, merged_from, is_learned, parent_topic_id,
                   parent_topic_title, is_subtopic, lesson_id, learning_state, practice_allowed)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24,$25,$26,$27,$28)
                   ON CONFLICT (id) DO UPDATE SET
                     title=EXCLUDED.title, description=EXCLUDED.description,
                     section_number=EXCLUDED.section_number, content_chunk=EXCLUDED.content_chunk,
                     order_idx=EXCLUDED.order_idx, cost_mins=EXCLUDED.cost_mins,
                     mastery=EXCLUDED.mastery, p_l0=EXCLUDED.p_l0, p_t=EXCLUDED.p_t,
                     p_g=EXCLUDED.p_g, p_s=EXCLUDED.p_s,
                     awaiting_diagnostic=EXCLUDED.awaiting_diagnostic,
                     fsrs_card=EXCLUDED.fsrs_card, fsrs_stability=EXCLUDED.fsrs_stability,
                     fsrs_difficulty=EXCLUDED.fsrs_difficulty,
                     fsrs_last_review=EXCLUDED.fsrs_last_review,
                     fsrs_due_date=EXCLUDED.fsrs_due_date,
                     merged_from=EXCLUDED.merged_from,
                     is_learned=EXCLUDED.is_learned,
                     parent_topic_id=EXCLUDED.parent_topic_id,
                     parent_topic_title=EXCLUDED.parent_topic_title,
                     is_subtopic=EXCLUDED.is_subtopic,
                     lesson_id=EXCLUDED.lesson_id,
                     learning_state=EXCLUDED.learning_state,
                     practice_allowed=EXCLUDED.practice_allowed""",
                t.id, t.subject_id, t.user_id, t.title, t.description, t.section_number,
                t.content_chunk, t.order_idx, t.cost_mins,
                t.mastery, t.p_l0, t.p_t, t.p_g, t.p_s,
                t.awaiting_diagnostic, t.fsrs_card,
                t.fsrs_stability, t.fsrs_difficulty,
                t.fsrs_last_review, t.fsrs_due_date,
                t.merged_from, t.is_learned, t.parent_topic_id, t.parent_topic_title,
                t.is_subtopic, t.lesson_id, t.learning_state, t.practice_allowed,
            )


async def update_topic(pool: asyncpg.Pool, topic: Topic) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE topics SET mastery=$2, p_l0=$3, p_t=$4, p_g=$5, p_s=$6,
               awaiting_diagnostic=$7, fsrs_card=$8, fsrs_stability=$9,
               fsrs_difficulty=$10, fsrs_last_review=$11, fsrs_due_date=$12,
               cost_mins=$13, is_learned=$14, parent_topic_id=$15, parent_topic_title=$16,
               is_subtopic=$17, lesson_id=$18, learning_state=$19,
               practice_allowed=$20, mastery_confidence=$21, mastery_evidence_source=$22 WHERE id=$1""",
            topic.id, topic.mastery, topic.p_l0, topic.p_t, topic.p_g, topic.p_s,
            topic.awaiting_diagnostic, topic.fsrs_card,
            topic.fsrs_stability, topic.fsrs_difficulty,
            topic.fsrs_last_review, topic.fsrs_due_date, topic.cost_mins,
            topic.is_learned, topic.parent_topic_id, topic.parent_topic_title,
            topic.is_subtopic, topic.lesson_id, topic.learning_state, topic.practice_allowed,
            topic.mastery_confidence, topic.mastery_evidence_source,
        )


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

async def get_weekly_tasks(
    pool: asyncpg.Pool, user_id: str, subject_id: str, from_date: date
) -> list[StudyTask]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM study_tasks WHERE user_id=$1 AND subject_id=$2 AND scheduled_date >= $3 ORDER BY scheduled_date",
            user_id, subject_id, from_date,
        )
    return [_row_to_task(r) for r in rows]


async def get_task(pool: asyncpg.Pool, user_id: str, task_id: str) -> StudyTask | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM study_tasks WHERE user_id=$1 AND id=$2",
            user_id,
            task_id,
        )
    return _row_to_task(row) if row else None


async def delete_future_tasks(
    pool: asyncpg.Pool, user_id: str, subject_id: str, from_date: date
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM study_tasks WHERE user_id=$1 AND subject_id=$2 AND scheduled_date >= $3 AND status='ready'",
            user_id, subject_id, from_date,
        )


async def delete_future_tasks_all_subjects(
    pool: asyncpg.Pool, user_id: str, from_date: date
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM study_tasks WHERE user_id=$1 AND scheduled_date >= $2 AND status='ready'",
            user_id, from_date,
        )


async def insert_study_tasks(pool: asyncpg.Pool, tasks: list[dict]) -> None:
    if not tasks:
        return
    # Extract unique topic IDs from tasks to verify their existence
    topic_ids = {t["topic_id"] for t in tasks if t.get("topic_id")}
    
    async with pool.acquire() as conn:
        valid_topic_ids = set()
        if topic_ids:
            rows = await conn.fetch(
                "SELECT id FROM topics WHERE id = ANY($1::text[])",
                list(topic_ids),
            )
            valid_topic_ids = {r["id"] for r in rows}

        for t in tasks:
            scheduled = t["scheduled_date"]
            if isinstance(scheduled, str):
                scheduled = date.fromisoformat(scheduled)
            day = scheduled.strftime("%a")
            
            # Prevent ForeignKeyViolationError by defaulting to None if topic doesn't exist
            topic_id = t.get("topic_id")
            if topic_id and topic_id not in valid_topic_ids:
                topic_id = None
                
            try:
                await conn.execute(
                    """INSERT INTO study_tasks (id, subject_id, topic_id, user_id, topic_title,
                       type, duration_minutes, reason, scheduled_date, status, day, title, start_at, end_at, priority,
                       lesson_id, lesson_title, learning_state, subtopic_id, parent_topic_id,
                       is_partial_topic, scope, earliest_allowed_at)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23)
                       ON CONFLICT (id) DO NOTHING""",
                    t["id"], t["subject_id"], topic_id, t["user_id"],
                    t["topic_title"], t["type"], t["duration_minutes"],
                    t.get("reason", ""), scheduled, t.get("status", "ready"), day,
                    t.get("title"), t.get("start_at"), t.get("end_at"), t.get("priority", "medium"),
                    t.get("lesson_id"), t.get("lesson_title"), t.get("learning_state"),
                    t.get("subtopic_id") or topic_id, t.get("parent_topic_id"),
                    t.get("is_partial_topic", False), t.get("scope"), t.get("earliest_allowed_at"),
                )
            except asyncpg.exceptions.ForeignKeyViolationError:
                # Fallback: if foreign key is still violated due to concurrent deletes, insert with topic_id=None
                try:
                    await conn.execute(
                        """INSERT INTO study_tasks (id, subject_id, topic_id, user_id, topic_title,
                           type, duration_minutes, reason, scheduled_date, status, day, title, start_at, end_at, priority,
                           lesson_id, lesson_title, learning_state, subtopic_id, parent_topic_id,
                           is_partial_topic, scope, earliest_allowed_at)
                           VALUES ($1,$2,NULL,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23)
                           ON CONFLICT (id) DO NOTHING""",
                        t["id"], t["subject_id"], t["user_id"],
                        t["topic_title"], t["type"], t["duration_minutes"],
                        t.get("reason", ""), scheduled, t.get("status", "ready"), day,
                        t.get("title"), t.get("start_at"), t.get("end_at"), t.get("priority", "medium"),
                        t.get("lesson_id"), t.get("lesson_title"), t.get("learning_state"),
                        t.get("subtopic_id") or topic_id, t.get("parent_topic_id"),
                        t.get("is_partial_topic", False), t.get("scope"), t.get("earliest_allowed_at"),
                    )
                except Exception:
                    pass
            except Exception:
                pass


async def update_task_status(pool: asyncpg.Pool, task_id: str, status: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute("UPDATE study_tasks SET status=$2 WHERE id=$1", task_id, status)


# ---------------------------------------------------------------------------
# Quiz sessions & questions
# ---------------------------------------------------------------------------

async def get_quiz_session(pool: asyncpg.Pool, session_id: str) -> QuizSession | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM quiz_sessions WHERE id=$1", session_id)
        if not row:
            return None
        session = _row_to_session(row)
        q_rows = await conn.fetch(
            "SELECT * FROM quiz_questions WHERE session_id=$1 ORDER BY id", session_id
        )
        session.questions = [_row_to_question(qr) for qr in q_rows]
    return session


async def save_quiz_session(pool: asyncpg.Pool, session: QuizSession) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO quiz_sessions (id, subject_id, task_id, user_id, is_diagnostic)
               VALUES ($1,$2,$3,$4,$5) ON CONFLICT (id) DO NOTHING""",
            session.id, session.subject_id, session.task_id, session.user_id, session.is_diagnostic,
        )
        for q in session.questions:
            await conn.execute(
                """INSERT INTO quiz_questions (id, session_id, topic_id, user_id, prompt, options,
                   correct_option, explanation, source)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) ON CONFLICT (id) DO NOTHING""",
                q.id, session.id, q.topic_id, session.user_id,
                q.prompt, q.options, q.correct_option, q.explanation, q.source,
            )


async def update_quiz_question(
    pool: asyncpg.Pool, question_id: str, selected_option: str, is_correct: bool
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE quiz_questions SET selected_option=$2, is_correct=$3 WHERE id=$1",
            question_id, selected_option, is_correct,
        )


async def insert_session_mastery_deltas(
    pool: asyncpg.Pool, session_id: str, deltas: list[dict]
) -> None:
    async with pool.acquire() as conn:
        for d in deltas:
            await conn.execute(
                """INSERT INTO session_mastery_deltas (session_id, topic_id, delta)
                   VALUES ($1,$2,$3) ON CONFLICT (session_id, topic_id) DO UPDATE SET delta=EXCLUDED.delta""",
                session_id, d["topic_id"], d["delta"],
            )


async def update_session_result(
    pool: asyncpg.Pool, session_id: str, correct: int, total: int,
    xp_earned: int, feedback: str,
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE quiz_sessions SET submitted_at=now(), correct=$2, total=$3,
               xp_earned=$4, feedback=$5 WHERE id=$1""",
            session_id, correct, total, xp_earned, feedback,
        )


# ---------------------------------------------------------------------------
# FSRS review logs (append-only)
# ---------------------------------------------------------------------------

async def append_review_log(pool: asyncpg.Pool, log: FsrsReviewLog) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO fsrs_review_logs (id, user_id, subject_id, item_id, rating,
               review_date, elapsed_days, review_state) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)""",
            log.id, log.user_id, log.subject_id, log.item_id, log.rating,
            log.review_date, log.elapsed_days, log.review_state,
        )


async def get_review_logs(pool: asyncpg.Pool, user_id: str) -> list[FsrsReviewLog]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM fsrs_review_logs WHERE user_id=$1 ORDER BY review_date", user_id
        )
    return [
        FsrsReviewLog(
            id=r["id"], user_id=r["user_id"], subject_id=r["subject_id"],
            item_id=r["item_id"], rating=r["rating"],
            review_date=r["review_date"].isoformat() if hasattr(r["review_date"], "isoformat") else str(r["review_date"]),
            elapsed_days=r["elapsed_days"], review_state=r["review_state"],
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Misc — achievements & notifications (mock stubs)
# ---------------------------------------------------------------------------

async def get_achievements(pool: asyncpg.Pool, user_id: str) -> list[dict]:
    async with pool.acquire() as conn:
        val = await conn.fetchval("SELECT achievements FROM users WHERE id=$1", user_id)
    return _j(val, [])


async def get_notifications(pool: asyncpg.Pool, user_id: str) -> list[dict]:
    # Notifications stored in users.notifications JSONB as a dict; return list
    async with pool.acquire() as conn:
        val = await conn.fetchval("SELECT notifications FROM users WHERE id=$1", user_id)
    if isinstance(val, str):
        val = json.loads(val)
    if isinstance(val, dict):
        return [{"id": k, **v} if isinstance(v, dict) else {"id": k, "enabled": bool(v)} for k, v in val.items()]
    return val or []


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

async def get_user_by_email(pool: asyncpg.Pool, email: str) -> UserProfile | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE lower(email)=lower($1)", email)
    return _row_to_profile(row) if row else None

async def get_user_by_username(pool: asyncpg.Pool, username: str) -> UserProfile | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE lower(username)=lower($1)", username)
    return _row_to_profile(row) if row else None

async def get_user_by_identifier(pool: asyncpg.Pool, identifier: str) -> UserProfile | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM users WHERE lower(email)=lower($1) OR lower(username)=lower($1)",
            identifier,
        )
    return _row_to_profile(row) if row else None


async def get_password_hash(pool: asyncpg.Pool, user_id: str) -> str | None:
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT password_hash FROM users WHERE id=$1", user_id)


async def create_user(
    pool: asyncpg.Pool, user_id: str, email: str, password_hash: str, username: str | None = None
) -> UserProfile:
    from app.db.schema_defaults import DEFAULT_STUDY_DAYS, DEFAULT_DAILY_GOAL_MINUTES, DEFAULT_MASCOT_TONE
    username = username or user_id.removeprefix("user-")
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO users (id, username, email, password_hash, study_days, daily_goal_minutes, mascot_tone)
               VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING *""",
            user_id, username, email, password_hash, DEFAULT_STUDY_DAYS,
            DEFAULT_DAILY_GOAL_MINUTES, DEFAULT_MASCOT_TONE,
        )
    return _row_to_profile(row)

async def ensure_admin_user(pool: asyncpg.Pool, password_hash: str) -> None:
    from app.db.schema_defaults import DEFAULT_STUDY_DAYS, DEFAULT_DAILY_GOAL_MINUTES, DEFAULT_MASCOT_TONE
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS username TEXT")
            await conn.execute(
                """UPDATE users
                   SET username = left(COALESCE(username, 'admin') || '-legacy-' || substr(md5(id), 1, 8), 63)
                   WHERE lower(username) = 'admin' AND id <> 'user-admin'"""
            )
            await conn.execute(
                """UPDATE users
                   SET email = 'admin-legacy-' || substr(md5(id), 1, 8) || '@local.studyflow'
                   WHERE lower(email) = 'admin@local.studyflow' AND id <> 'user-admin'"""
            )
            await conn.execute(
                """INSERT INTO users (id, username, email, password_hash, study_days, daily_goal_minutes, mascot_tone)
                   VALUES ('user-admin','admin','admin@local.studyflow',$1,$2,$3,$4)
                   ON CONFLICT (id) DO UPDATE SET
                     username=EXCLUDED.username,
                     email=EXCLUDED.email,
                     password_hash=EXCLUDED.password_hash""",
                password_hash,
                DEFAULT_STUDY_DAYS,
                DEFAULT_DAILY_GOAL_MINUTES,
                DEFAULT_MASCOT_TONE,
            )
            await conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username)")


async def ensure_busy_events_table(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS busy_events (
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
                )
                """
            )
            await conn.execute("ALTER TABLE busy_events ADD COLUMN IF NOT EXISTS recurrence_id TEXT")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_busy_events_user_time ON busy_events(user_id, start_at, end_at)")
            await conn.execute(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_trigger WHERE tgname = 'busy_events_updated_at'
                    ) THEN
                        CREATE TRIGGER busy_events_updated_at BEFORE UPDATE ON busy_events
                        FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
                    END IF;
                END $$;
                """
            )

async def ensure_topic_mastery_evidence_columns(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("ALTER TABLE topics ADD COLUMN IF NOT EXISTS mastery_confidence REAL NOT NULL DEFAULT 0")
            await conn.execute("ALTER TABLE topics ADD COLUMN IF NOT EXISTS mastery_evidence_source TEXT NOT NULL DEFAULT 'none'")
            await conn.execute(
                """UPDATE topics
                   SET mastery_confidence=0.9,
                       mastery_evidence_source='quiz'
                   WHERE mastery_confidence=0
                     AND (is_learned=true OR awaiting_diagnostic=false OR fsrs_last_review IS NOT NULL)"""
            )


async def get_recent_topic_questions(
    pool: asyncpg.Pool, topic_id: str, user_id: str, limit: int
) -> list[QuizQuestion]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT DISTINCT ON (prompt) *
               FROM quiz_questions
               WHERE topic_id=$1 AND user_id=$2
               ORDER BY prompt, created_at DESC
               LIMIT $3""",
            topic_id, user_id, limit
        )
        return [_row_to_question(r) for r in rows]


async def get_tasks_before_date_with_status(
    pool: asyncpg.Pool, user_id: str, before_date: date, status: str
) -> list[StudyTask]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM study_tasks WHERE user_id=$1 AND scheduled_date < $2 AND status=$3",
            user_id, before_date, status
        )
    return [_row_to_task(r) for r in rows]


async def bulk_update_task_status(
    pool: asyncpg.Pool, task_ids: list[str], status: str
) -> None:
    if not task_ids:
        return
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE study_tasks SET status=$1 WHERE id = ANY($2)",
            status, task_ids
        )


async def get_weekly_tasks_all_subjects(
    pool: asyncpg.Pool, user_id: str, from_date: date
) -> list[StudyTask]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM study_tasks WHERE user_id=$1 AND scheduled_date >= $2 ORDER BY scheduled_date",
            user_id, from_date,
        )
    return [_row_to_task(r) for r in rows]


async def ensure_mastery_events_table(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
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
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_mastery_events_topic ON mastery_events (topic_id, created_at)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_mastery_events_user ON mastery_events (user_id, created_at)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_mastery_events_format ON mastery_events (question_format) WHERE NOT excluded")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_mastery_events_eval ON mastery_events (excluded, created_at)")


async def append_mastery_event(
    pool: asyncpg.Pool,
    user_id: str,
    subject_id: str,
    topic_id: str,
    source_type: str,
    source_id: str,
    question_format: str | None,
    is_diagnostic: bool,
    p_l_before: float,
    p_t_used: float,
    p_g_used: float,
    p_s_used: float,
    predicted_p_correct: float,
    actual_correct: bool,
    p_l_obs: float,
    p_l_after: float,
    excluded: bool = False,
    exclude_reason: str | None = None,
) -> None:
    event_id = f"evt_{uuid.uuid4().hex[:10]}"
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO mastery_events (
                id, user_id, subject_id, topic_id, source_type, source_id, question_format, is_diagnostic,
                p_l_before, p_t_used, p_g_used, p_s_used, predicted_p_correct, actual_correct,
                p_l_obs, p_l_after, excluded, exclude_reason, created_at
               ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,now())""",
            event_id, user_id, subject_id, topic_id, source_type, source_id, question_format, is_diagnostic,
            p_l_before, p_t_used, p_g_used, p_s_used, predicted_p_correct, actual_correct,
            p_l_obs, p_l_after, excluded, exclude_reason,
        )


async def get_recent_mastery_events(
    pool: asyncpg.Pool,
    topic_id: str,
    user_id: str,
    days: int,
    limit: int,
) -> list[asyncpg.Record]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT source_type, source_id, question_format, is_diagnostic, predicted_p_correct,
                      actual_correct, created_at
               FROM mastery_events
               WHERE topic_id=$1
                 AND user_id=$2
                 AND NOT excluded
                 AND created_at >= now() - make_interval(days => $3)
               ORDER BY created_at DESC
               LIMIT $4""",
            topic_id,
            user_id,
            days,
            limit,
        )
    return list(rows)



