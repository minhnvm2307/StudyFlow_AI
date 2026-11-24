from __future__ import annotations

import asyncio
import json
import hashlib
import logging
import os
import re
import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

import asyncpg
from fastapi import BackgroundTasks

from app.config import settings
from app.core.document.extractor import extract_text_from_file_path, sanitize_text_for_postgres
from app.core.document.llm_section_split import complete_json, complete_text
from app.core.rag.llm_topic_extractor import extract_topics_via_llm
from app.core.rag.pipeline import assign_topics_to_chunks, build_sections, create_chunks, extract_topics, parse_pages
from app.core.rag.retrieval import retrieve_chunks, retrieve_multi_hop_rag, source_ref_from_chunk
from app.core.rag.text import normalize_for_search
from app.core.scheduler import FSRSScheduler, get_scheduler
from app.core.rag.prompts import ROUTER_SYSTEM_PROMPT, GENERAL_TUTOR_SYSTEM_PROMPT, RAG_TUTOR_SYSTEM_PROMPT
from app.db import repository
from app.schemas import FsrsReviewLog
from app.services.mastery_service import BatchQuestionOutcome, apply_objective_batch, apply_self_assessment_seed
from app.services.syllabus_service import parse_syllabus_payload, score_lesson_match


DEFAULT_USER_ID = "user-demo"
RATING_TO_INT = {"Again": 1, "Hard": 2, "Good": 3, "Easy": 4}
MAX_OVERLAPPING_SEMESTER_COURSES = 5
logger = logging.getLogger("studyflow")


def _username_from_user_id(user_id: str) -> str:
    value = re.sub(r"[^a-z0-9_.-]+", "-", user_id.lower().removeprefix("user-")).strip("-.")
    return value if len(value) >= 3 else f"user-{value or 'dev'}"


async def ensure_dev_user(pool: asyncpg.Pool, user_id: str = DEFAULT_USER_ID) -> None:
    async with pool.acquire() as conn:
        await conn.execute("ALTER TABLE subjects ADD COLUMN IF NOT EXISTS availability_windows JSONB NOT NULL DEFAULT '[]'::jsonb")
        await conn.execute(
            """INSERT INTO users (id, username, email, password_hash, study_days, daily_goal_minutes, mascot_tone)
               VALUES ($1,$2,$3,NULL,$4,$5,$6)
               ON CONFLICT (id) DO NOTHING""",
            user_id,
            _username_from_user_id(user_id),
            f"{user_id}@local.studyflow",
            ["Mon", "Tue", "Wed", "Thu", "Fri"],
            30,
            "encouraging",
        )


async def dev_clear(pool: asyncpg.Pool, user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM users WHERE id=$1", user_id)
    await ensure_dev_user(pool, user_id)
    return {"ok": True, "data": {"users": [{"id": user_id, "name": "StudyFlow Test User", "email": f"{user_id}@local.studyflow"}]}}


async def dev_reset(pool: asyncpg.Pool, user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
    await dev_clear(pool, user_id)
    biology = await create_course(pool, {
        "name": "Biology Final Review",
        "mode": "exam_sprint",
        "priority": "high",
        "targetScore": 88,
        "examDate": "2026-07-30",
    }, user_id)
    await create_syllabus(pool, biology["id"], {
        "mode": "manual",
        "currentWeek": 1,
        "currentLessonNumber": 1,
        "lessons": [
            {"weekNumber": 1, "lessonNumber": 1, "title": "Plant energy foundations", "assignedReadings": ["Chapter 1"]},
            {"weekNumber": 2, "lessonNumber": 2, "title": "Respiration and ATP", "assignedReadings": ["Chapter 2"]},
        ],
    }, user_id)
    await create_source(pool, biology["id"], {
        "filename": "biology-photosynthesis-notes.txt",
        "fileType": "txt",
        "text": "Chapter 1: Plant Energy\n\nTopic: Photosynthesis\n\nPhotosynthesis converts light energy, carbon dioxide, and water into glucose and oxygen. Chlorophyll in chloroplasts captures light energy.\n\nChapter 2: Respiration\n\nCellular respiration releases ATP from glucose.",
    }, user_id)
    await generate_plan(pool, biology["id"], {}, user_id)
    return {"ok": True, "data": {"courses": [biology]}}


async def list_courses(pool: asyncpg.Pool, user_id: str = DEFAULT_USER_ID, filter_value: str | None = None, sort: str | None = None) -> list[dict[str, Any]]:
    await ensure_dev_user(pool, user_id)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT s.*,
                      (SELECT COUNT(*) FROM course_sources cs WHERE cs.subject_id=s.id) AS source_count,
                      (SELECT COUNT(*) FROM topics t WHERE t.subject_id=s.id) AS topic_count,
                      (SELECT COUNT(*) FROM study_tasks st WHERE st.subject_id=s.id) AS task_count,
                      COALESCE((SELECT AVG(t.mastery) FROM topics t WHERE t.subject_id=s.id), 0) AS mastery_avg,
                      COALESCE((SELECT AVG(t.mastery_confidence) FROM topics t WHERE t.subject_id=s.id), 0) AS confidence_avg,
                      (SELECT sy.status FROM course_syllabi sy WHERE sy.subject_id=s.id ORDER BY sy.created_at DESC LIMIT 1) AS syllabus_status,
                      (SELECT sy.current_week FROM course_syllabi sy WHERE sy.subject_id=s.id ORDER BY sy.created_at DESC LIMIT 1) AS current_week,
                      (SELECT sy.current_lesson_id FROM course_syllabi sy WHERE sy.subject_id=s.id ORDER BY sy.created_at DESC LIMIT 1) AS current_lesson_id,
                      (SELECT sl.title FROM course_syllabi sy JOIN syllabus_lessons sl ON sl.id=sy.current_lesson_id WHERE sy.subject_id=s.id ORDER BY sy.created_at DESC LIMIT 1) AS current_lesson_title
               FROM subjects s
               WHERE s.user_id=$1
               ORDER BY s.updated_at DESC""",
            user_id,
        )
    courses = [_course_from_row(row) for row in rows]
    if filter_value == "featured":
        courses = [c for c in courses if c.get("featured") or c.get("priority") == "high" or c.get("status") == "needs_attention"]
    if filter_value == "shared":
        courses = [c for c in courses if c.get("shared")]
    if sort == "recent":
        courses.sort(key=lambda c: c.get("updatedAt") or "", reverse=True)
    return courses


async def get_course(pool: asyncpg.Pool, course_id: str, user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
    row = await _course_row(pool, course_id, user_id)
    if not row:
        raise KeyError("Course not found")
    return _course_from_row(row)


async def create_course(pool: asyncpg.Pool, payload: dict[str, Any], user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
    await ensure_dev_user(pool, user_id)
    name = str(payload.get("name") or "").strip()
    if not name:
        raise ValueError("Course name is required")
    course_id = f"course_{uuid.uuid4().hex[:10]}"
    mode = _course_mode_to_subject(payload.get("mode") or "continuous")
    priority = str(payload.get("priority") or "medium")
    exam_date = _parse_date(payload.get("examDate"))
    target_score = int(payload["targetScore"]) if payload.get("targetScore") not in (None, "") else None
    availability_windows = _normalize_availability_windows(payload.get("availabilityWindows")) if "availabilityWindows" in payload else []
    days_available = _availability_window_days(availability_windows) or _normalize_availability(payload.get("availability"))
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO subjects (id, user_id, name, mode, exam_date, daily_goal_minutes, is_priority,
                                      target_score, priority, featured, shared, days_available, availability_windows)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)""",
            course_id,
            user_id,
            name,
            mode,
            exam_date,
            int(payload.get("dailyGoalMinutes") or 30),
            priority == "high",
            target_score,
            priority,
            bool(payload.get("featured")),
            bool(payload.get("shared")),
            days_available,
            availability_windows,
        )
    if payload.get("autoGeneratePlan", True) is not False:
        await _auto_generate_initial_plan(pool, course_id, payload, user_id)
    return await get_course(pool, course_id, user_id)


async def validate_course_semester_overlap_limit(
    pool: asyncpg.Pool,
    payload: dict[str, Any],
    user_id: str = DEFAULT_USER_ID,
    *,
    exclude_course_id: str | None = None,
) -> None:
    start_date, end_date = _semester_window_from_payload(payload)
    if not start_date or not end_date:
        return
    if end_date < start_date:
        raise ValueError("semesterEndDate must be after semesterStartDate")

    windows = await _list_latest_semester_windows(pool, user_id, exclude_course_id=exclude_course_id)
    max_overlap, breach_day = _max_semester_overlap([
        *windows,
        {"courseId": exclude_course_id or "__candidate__", "startDate": start_date, "endDate": end_date},
    ])
    if max_overlap > MAX_OVERLAPPING_SEMESTER_COURSES:
        breach_text = breach_day.isoformat() if breach_day else "một khoảng thời gian trong học kỳ"
        raise ValueError(
            f"Bạn chỉ có thể có tối đa {MAX_OVERLAPPING_SEMESTER_COURSES} môn học chồng thời gian trong cùng một học kỳ. "
            f"Khoảng học kỳ này vượt giới hạn vào ngày {breach_text}."
        )


async def update_course(pool: asyncpg.Pool, course_id: str, payload: dict[str, Any], user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    if "name" in payload:
        fields["name"] = str(payload["name"]).strip()
    if "mode" in payload:
        fields["mode"] = _course_mode_to_subject(payload["mode"])
    if "examDate" in payload:
        fields["exam_date"] = _parse_date(payload["examDate"])
    if "targetScore" in payload:
        fields["target_score"] = int(payload["targetScore"]) if payload["targetScore"] not in (None, "") else None
    if "priority" in payload:
        fields["priority"] = payload["priority"]
        fields["is_priority"] = payload["priority"] == "high"
    if "featured" in payload:
        fields["featured"] = bool(payload["featured"])
    if "shared" in payload:
        fields["shared"] = bool(payload["shared"])
    if "availabilityWindows" in payload:
        windows = _normalize_availability_windows(payload.get("availabilityWindows"))
        fields["availability_windows"] = windows
        fields["days_available"] = _availability_window_days(windows)
    elif "availability" in payload:
        fields["days_available"] = _normalize_availability(payload.get("availability"))
    if fields:
        sets = []
        values = [course_id, user_id]
        for key, value in fields.items():
            values.append(value)
            sets.append(f"{key}=${len(values)}")
        async with pool.acquire() as conn:
            await conn.execute(f"UPDATE subjects SET {', '.join(sets)} WHERE id=$1 AND user_id=$2", *values)
    return await get_course(pool, course_id, user_id)


async def delete_course(pool: asyncpg.Pool, course_id: str, user_id: str = DEFAULT_USER_ID) -> None:
    await _require_course(pool, course_id, user_id)
    async with pool.acquire() as conn:
        storage_paths = await conn.fetch(
            "SELECT storage_path FROM course_sources WHERE subject_id=$1 AND user_id=$2 AND storage_path IS NOT NULL",
            course_id,
            user_id,
        )
        async with conn.transaction():
            await conn.execute("DELETE FROM chat_messages WHERE thread_id IN (SELECT id FROM chat_threads WHERE subject_id=$1 AND user_id=$2)", course_id, user_id)
            await conn.execute("DELETE FROM chat_threads WHERE subject_id=$1 AND user_id=$2", course_id, user_id)
            await conn.execute("DELETE FROM flashcard_sessions WHERE subject_id=$1 AND user_id=$2", course_id, user_id)
            await conn.execute("DELETE FROM flashcards WHERE subject_id=$1 AND user_id=$2", course_id, user_id)
            await conn.execute("DELETE FROM practice_quiz_results WHERE quiz_id IN (SELECT id FROM practice_quizzes WHERE subject_id=$1 AND user_id=$2) OR subject_id=$1", course_id, user_id)
            await conn.execute("DELETE FROM practice_quizzes WHERE subject_id=$1 AND user_id=$2", course_id, user_id)
            await conn.execute("DELETE FROM study_tasks WHERE subject_id=$1 AND user_id=$2", course_id, user_id)
            await conn.execute("DELETE FROM lesson_material_mappings WHERE lesson_id IN (SELECT id FROM topics WHERE subject_id=$1 AND user_id=$2)", course_id, user_id)
            await conn.execute("DELETE FROM topics WHERE subject_id=$1 AND user_id=$2", course_id, user_id)
            await conn.execute("DELETE FROM course_syllabi WHERE subject_id=$1 AND user_id=$2", course_id, user_id)
            await conn.execute("DELETE FROM document_chunks WHERE subject_id=$1 AND user_id=$2", course_id, user_id)
            await conn.execute("DELETE FROM course_sources WHERE subject_id=$1 AND user_id=$2", course_id, user_id)
            await conn.execute("DELETE FROM fsrs_review_logs WHERE user_id=$1 AND subject_id=$2", user_id, course_id)
            await conn.execute("DELETE FROM subjects WHERE id=$1 AND user_id=$2", course_id, user_id)

    for row in storage_paths:
        _delete_local_course_file(row["storage_path"])


def _delete_local_course_file(path: str | None) -> None:
    if not path:
        return
    try:
        target = os.path.abspath(path)
        cwd = os.getcwd()
        allowed_roots = [
            os.path.abspath(os.path.join(cwd, "data", "uploads")),
            os.path.abspath(os.path.join(cwd, "backend", "data", "uploads")),
        ]
        if not any(os.path.commonpath([root, target]) == root for root in allowed_roots):
            return
        if os.path.isfile(target):
            os.remove(target)
    except Exception:
        return


async def list_sources(pool: asyncpg.Pool, course_id: str, user_id: str = DEFAULT_USER_ID) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM course_sources WHERE subject_id=$1 AND user_id=$2 ORDER BY created_at DESC", course_id, user_id)
    return [_source_from_row(row) for row in rows]


async def create_source(pool: asyncpg.Pool, course_id: str, payload: dict[str, Any], user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
    await ensure_dev_user(pool, user_id)
    await _require_course(pool, course_id, user_id)
    source_id = f"source_{uuid.uuid4().hex[:10]}"
    filename = str(payload.get("filename") or payload.get("url") or "pasted-text.txt")
    original_name = str(payload.get("originalName") or payload.get("original_name") or filename)
    text_content = sanitize_text_for_postgres(payload.get("text") or payload.get("text_content") or payload.get("url") or "")
    file_type = str(payload.get("fileType") or payload.get("file_type") or _file_type(filename))
    mime_type = str(payload.get("mimeType") or payload.get("mime_type") or "text/plain")

    s3_url = payload.get("url")
    storage_path = payload.get("storagePath") or payload.get("storage_path")
    from app.config import settings
    if not s3_url and storage_path and os.path.exists(storage_path) and settings.S3_BUCKET_NAME:
        try:
            from app.core.document.extractor import upload_file_to_s3
            with open(storage_path, "rb") as f:
                file_bytes = f.read()
            safe_name = "".join(c for c in filename if c.isalnum() or c in (".", "_", "-")).strip()
            s3_key = f"sources/{user_id}/{course_id}/{uuid.uuid4().hex[:8]}_{safe_name}"
            s3_url = upload_file_to_s3(file_bytes, s3_key)
            try:
                os.remove(storage_path)
            except Exception:
                pass
            storage_path = None
        except Exception as e:
            print(f"Failed to upload source to S3: {e}")

    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO course_sources (id, subject_id, user_id, filename, original_name, file_type, mime_type,
                                           status, selected, topic_count, url, text_content, storage_path)
               VALUES ($1,$2,$3,$4,$5,$6,$7,'parsing',$8,0,$9,$10,$11)""",
            source_id,
            course_id,
            user_id,
            filename,
            original_name,
            file_type,
            mime_type,
            bool(payload.get("selected", True)),
            s3_url,
            text_content,
            storage_path,
        )
    await process_source(pool, source_id, user_id)
    await _auto_rebuild_course_plan(pool, course_id, user_id)
    return await get_source(pool, source_id, user_id)

async def create_pending_source(pool: asyncpg.Pool, course_id: str, payload: dict[str, Any], user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
    await ensure_dev_user(pool, user_id)
    await _require_course(pool, course_id, user_id)
    source_id = f"source_{uuid.uuid4().hex[:10]}"
    filename = str(payload.get("filename") or "upload.txt")
    original_name = str(payload.get("originalName") or payload.get("original_name") or filename)
    file_type = str(payload.get("fileType") or payload.get("file_type") or _file_type(filename))
    mime_type = str(payload.get("mimeType") or payload.get("mime_type") or "application/octet-stream")
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO course_sources (id, subject_id, user_id, filename, original_name, file_type, mime_type,
                                           status, selected, topic_count, url, text_content, storage_path)
               VALUES ($1,$2,$3,$4,$5,$6,$7,'parsing',$8,0,$9,'',$10)""",
            source_id,
            course_id,
            user_id,
            filename,
            original_name,
            file_type,
            mime_type,
            bool(payload.get("selected", True)),
            payload.get("url"),
            payload.get("storagePath") or payload.get("storage_path"),
        )
    return await get_source(pool, source_id, user_id)

async def process_source_file(pool: asyncpg.Pool, source_id: str, user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
    source = await get_source(pool, source_id, user_id)
    storage_path = source.get("storagePath")
    if not storage_path:
        raise ValueError("Source storage path is required")
    try:
        text = await asyncio.to_thread(lambda: sanitize_text_for_postgres(extract_text_from_file_path(storage_path)))
        s3_url = source.get("url")
        from app.config import settings
        if not s3_url and os.path.exists(storage_path) and settings.S3_BUCKET_NAME:
            try:
                from app.core.document.extractor import upload_file_to_s3
                with open(storage_path, "rb") as f:
                    file_bytes = f.read()
                filename = source.get("filename") or "upload.txt"
                safe_name = "".join(c for c in filename if c.isalnum() or c in (".", "_", "-")).strip()
                s3_key = f"sources/{user_id}/{source['courseId']}/{uuid.uuid4().hex[:8]}_{safe_name}"
                s3_url = upload_file_to_s3(file_bytes, s3_key)
            except Exception as e:
                print(f"Failed to upload source to S3 in process_source_file: {e}")

        async with pool.acquire() as conn:
            await conn.execute(
                """UPDATE course_sources 
                   SET text_content=$3, status='parsing', error_message=NULL, url=$4, storage_path=NULL 
                   WHERE id=$1 AND user_id=$2""",
                source_id,
                user_id,
                text,
                s3_url,
            )
        return await process_source(pool, source_id, user_id)
    except Exception as exc:
        async with pool.acquire() as conn:
            await conn.execute("UPDATE course_sources SET status='failed', error_message=$3 WHERE id=$1 AND user_id=$2", source_id, user_id, str(exc))
        raise
    finally:
        if storage_path and os.path.exists(storage_path):
            try:
                os.remove(storage_path)
            except Exception:
                pass


async def get_source(pool: asyncpg.Pool, source_id: str, user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM course_sources WHERE id=$1 AND user_id=$2", source_id, user_id)
    if not row:
        raise KeyError("Source not found")
    return _source_from_row(row)


async def update_source(pool: asyncpg.Pool, source_id: str, payload: dict[str, Any], user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
    allowed = {
        "filename": "filename",
        "fileType": "file_type",
        "status": "status",
        "selected": "selected",
        "topicCount": "topic_count",
        "errorMessage": "error_message",
    }
    fields = {column: payload[key] for key, column in allowed.items() if key in payload}
    if fields:
        values = [source_id, user_id]
        sets = []
        for key, value in fields.items():
            values.append(value)
            sets.append(f"{key}=${len(values)}")
        async with pool.acquire() as conn:
            await conn.execute(f"UPDATE course_sources SET {', '.join(sets)} WHERE id=$1 AND user_id=$2", *values)
    return await get_source(pool, source_id, user_id)


async def delete_source(pool: asyncpg.Pool, source_id: str, user_id: str = DEFAULT_USER_ID) -> None:
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM course_sources WHERE id=$1 AND user_id=$2", source_id, user_id)


async def create_syllabus(pool: asyncpg.Pool, course_id: str, payload: dict[str, Any], user_id: str = DEFAULT_USER_ID, status: str = "ready") -> dict[str, Any]:
    await ensure_dev_user(pool, user_id)
    await _require_course(pool, course_id, user_id)
    await validate_course_semester_overlap_limit(pool, payload, user_id, exclude_course_id=course_id)
    payload_mode = str(payload.get("mode") or payload.get("sourceType") or "manual").lower()
    payload_text = str(payload.get("text") or payload.get("rawText") or "").strip()
    if payload_mode in {"upload", "text"} and payload_text:
        mode, lessons, parsed = await asyncio.to_thread(parse_syllabus_payload, payload)
    else:
        mode, lessons, parsed = parse_syllabus_payload(payload)
    raw_text = str(payload.get("text") or payload.get("rawText") or "")
    chapters = payload.get("chapters")
    if not isinstance(chapters, list) and isinstance(parsed, dict):
        chapters = parsed.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        chapters = _chapters_from_lessons(lessons)
    if isinstance(chapters, list) and chapters:
        parsed = {**parsed, "chapters": chapters}
    parsed = _with_syllabus_metadata(parsed, payload, status, "Syllabus đang được thiết lập", 100)
    lessons, calendar_meta = _apply_class_calendar_to_lessons(lessons, payload)
    if calendar_meta:
        parsed = {**parsed, "calendar": calendar_meta}
    syllabus_id = f"syllabus_{uuid.uuid4().hex[:10]}"
    current_week = _int_or_none(payload.get("currentWeek")) or _int_or_none(payload.get("current_week"))
    current_lesson_number = _int_or_none(payload.get("currentLessonNumber")) or _int_or_none(payload.get("current_lesson_number"))
    if calendar_meta and payload.get("useCalendarProgress"):
        current_week = None
        current_lesson_number = None
    join_position = str(payload.get("joinPosition") or payload.get("join_position") or ("mid_semester" if current_week else "beginning"))
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM course_syllabi WHERE subject_id=$1 AND user_id=$2", course_id, user_id)
            if status == "review_pending":
                await conn.execute(
                    """INSERT INTO course_syllabi (id, subject_id, user_id, source_type, status, raw_text, parsed_json, current_week, join_position)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)""",
                    syllabus_id, course_id, user_id, mode, status,
                    raw_text, parsed, current_week, join_position,
                )
                await conn.execute("DELETE FROM syllabus_lessons WHERE subject_id=$1", course_id)
                await conn.execute("DELETE FROM study_tasks WHERE subject_id=$1 AND user_id=$2 AND status <> 'done'", course_id, user_id)
                return await get_syllabus(pool, course_id, user_id)

            await conn.execute("DELETE FROM study_tasks WHERE subject_id=$1 AND user_id=$2 AND status <> 'done'", course_id, user_id)
            await conn.execute("DELETE FROM topics WHERE subject_id=$1 AND user_id=$2", course_id, user_id)
            await conn.execute(
                """INSERT INTO course_syllabi (id, subject_id, user_id, source_type, status, raw_text, parsed_json, current_week, join_position)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)""",
                syllabus_id, course_id, user_id, mode, "skipped" if mode == "skip" else status,
                raw_text, parsed, current_week, join_position,
            )
            for index, lesson in enumerate(lessons):
                lesson_id = f"lesson_{uuid.uuid4().hex[:10]}"
                status = _lesson_status(lesson, index, current_week, current_lesson_number)
                if status == "current":
                    await conn.execute("UPDATE course_syllabi SET current_lesson_id=$2 WHERE id=$1", syllabus_id, lesson_id)
                await conn.execute(
                    """INSERT INTO syllabus_lessons (id, syllabus_id, subject_id, week_number, lesson_number, title,
                       description, assigned_readings, starts_on, ends_on, status, order_idx)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)""",
                    lesson_id, syllabus_id, course_id, lesson.get("week_number"), lesson.get("lesson_number"),
                    lesson.get("title") or f"Lesson {index + 1}", lesson.get("description") or "",
                    lesson.get("assigned_readings") or [], _parse_date(lesson.get("startsOn") or lesson.get("starts_on")),
                    _parse_date(lesson.get("endsOn") or lesson.get("ends_on")), status, int(lesson.get("order_idx") or index),
                )
    await map_syllabus(pool, course_id, user_id)
    await repository.set_plan_dirty(pool, user_id, True)
    return await get_syllabus(pool, course_id, user_id)


async def retry_uploaded_syllabus(pool: asyncpg.Pool, course_id: str, user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
    await ensure_dev_user(pool, user_id)
    await _require_course(pool, course_id, user_id)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM course_syllabi WHERE subject_id=$1 AND user_id=$2 ORDER BY created_at DESC LIMIT 1",
            course_id,
            user_id,
        )
    if not row or not str(row["raw_text"] or "").strip():
        raise ValueError("No uploaded syllabus text is available to retry. Upload the syllabus file again.")
    parsed_json = _json_value(row["parsed_json"], {})
    payload = {
        "mode": row["source_type"] or "upload",
        "text": row["raw_text"],
        "filename": parsed_json.get("filename"),
        "currentWeek": row["current_week"],
        "joinPosition": row["join_position"],
        "recoveryAction": "retry_uploaded_syllabus",
    }
    return await create_syllabus(pool, course_id, payload, user_id)


async def create_syllabus_from_sources(pool: asyncpg.Pool, course_id: str, user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
    await ensure_dev_user(pool, user_id)
    await _require_course(pool, course_id, user_id)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT filename, text_content
               FROM course_sources
               WHERE subject_id=$1 AND user_id=$2 AND COALESCE(text_content, '') <> ''
               ORDER BY selected DESC, created_at, id""",
            course_id,
            user_id,
        )
        current = await conn.fetchrow(
            "SELECT current_week, join_position FROM course_syllabi WHERE subject_id=$1 AND user_id=$2 ORDER BY created_at DESC LIMIT 1",
            course_id,
            user_id,
        )
    if not rows:
        raise ValueError("No textbook/source text is ready. Add or parse a textbook before creating a syllabus from it.")
    sections = []
    for row in rows:
        text = sanitize_text_for_postgres(row["text_content"])
        if text.strip():
            sections.append(f"Source: {row['filename']}\n{text}")
    payload = {
        "mode": "text",
        "text": "\n\n".join(sections),
        "filename": "generated-from-textbook-sources.txt",
        "currentWeek": current["current_week"] if current else None,
        "joinPosition": current["join_position"] if current else "beginning",
        "recoveryAction": "create_syllabus_from_sources",
    }
    return await create_syllabus(pool, course_id, payload, user_id)

async def create_processing_syllabus(pool: asyncpg.Pool, course_id: str, payload: dict[str, Any], user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
    await ensure_dev_user(pool, user_id)
    await _require_course(pool, course_id, user_id)
    await validate_course_semester_overlap_limit(pool, payload, user_id, exclude_course_id=course_id)
    syllabus_id = f"syllabus_{uuid.uuid4().hex[:10]}"
    current_week = _int_or_none(payload.get("currentWeek")) or _int_or_none(payload.get("current_week"))
    join_position = str(payload.get("joinPosition") or payload.get("join_position") or ("mid_semester" if current_week else "beginning"))
    raw_text = sanitize_text_for_postgres(payload.get("text") or payload.get("rawText") or "")
    parsed = _with_syllabus_metadata({}, payload, "uploaded", "Đã nhận file syllabus, đang chờ xử lý", 10)
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM course_syllabi WHERE subject_id=$1 AND user_id=$2", course_id, user_id)
            await conn.execute("DELETE FROM study_tasks WHERE subject_id=$1 AND user_id=$2 AND status <> 'done'", course_id, user_id)
            await conn.execute("DELETE FROM topics WHERE subject_id=$1 AND user_id=$2", course_id, user_id)
            await conn.execute(
                """INSERT INTO course_syllabi (id, subject_id, user_id, source_type, status, raw_text, parsed_json, current_week, join_position)
                   VALUES ($1,$2,$3,'upload','processing',$4,$5,$6,$7)""",
                syllabus_id,
                course_id,
                user_id,
                raw_text,
                parsed,
                current_week,
                join_position,
            )
    return await get_syllabus(pool, course_id, user_id)


async def mark_uploaded_syllabus_parse_failed(pool: asyncpg.Pool, course_id: str, payload: dict[str, Any], error: Exception | str, user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
    await ensure_dev_user(pool, user_id)
    await _require_course(pool, course_id, user_id)
    raw_text = sanitize_text_for_postgres(payload.get("text") or payload.get("rawText") or "")
    parsed = _with_syllabus_metadata(
        {"error": str(error), "recovery": {"canRetryUploadedSyllabus": bool(raw_text), "canCreateFromSources": True}},
        payload,
        "failed",
        "Không tách được syllabus từ file upload",
        100,
    )
    parsed["progress"] = {
        **parsed["progress"],
        "detail": str(error),
        "syllabus": {"status": "failed", "percent": 100, "message": "Thất bại"},
        "practice": {"status": "pending", "percent": 0, "message": "Chờ quyết định"},
        "schedule": {"status": "pending", "percent": 0, "message": "Chờ quyết định"},
    }
    async with pool.acquire() as conn:
        existing = await conn.fetchrow("SELECT id FROM course_syllabi WHERE subject_id=$1 AND user_id=$2 ORDER BY created_at DESC LIMIT 1", course_id, user_id)
        if existing:
            await conn.execute(
                """UPDATE course_syllabi
                   SET status='failed', raw_text=$3, parsed_json=COALESCE(parsed_json, '{}'::jsonb) || $4::jsonb
                   WHERE id=$1 AND user_id=$2""",
                existing["id"],
                user_id,
                raw_text,
                parsed,
            )
        else:
            await conn.execute(
                """INSERT INTO course_syllabi (id, subject_id, user_id, source_type, status, raw_text, parsed_json, join_position)
                   VALUES ($1,$2,$3,'upload','failed',$4,$5,'beginning')""",
                f"syllabus_{uuid.uuid4().hex[:10]}",
                course_id,
                user_id,
                raw_text,
                parsed,
            )
    return await get_syllabus(pool, course_id, user_id)


def _syllabus_progress(stage: str, message: str, percent: int, detail: str | None = None) -> dict[str, Any]:
    progress = {
        "stage": stage,
        "message": message,
        "percent": max(0, min(100, int(percent))),
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }
    if detail:
        progress["detail"] = detail
    return progress


def _with_syllabus_metadata(parsed: dict[str, Any], payload: dict[str, Any], stage: str, message: str, percent: int) -> dict[str, Any]:
    metadata = {
        "filename": payload.get("filename"),
        "storagePath": payload.get("storagePath") or payload.get("storage_path"),
        "progress": _syllabus_progress(stage, message, percent),
    }
    return {**metadata, **(parsed or {}), "progress": metadata["progress"]}


async def update_onboarding_progress(
    pool: asyncpg.Pool,
    course_id: str,
    user_id: str,
    stage: str,
    percent: int,
    message: str,
    syllabus_status: str,
    syllabus_percent: int,
    practice_status: str,
    practice_percent: int,
    schedule_status: str,
    schedule_percent: int,
    detail: str | None = None,
) -> None:
    progress_data = {
        "stage": stage,
        "percent": percent,
        "message": message,
        "detail": detail,
        "syllabus": {
            "status": syllabus_status,
            "percent": syllabus_percent,
            "message": "Trích xuất tài liệu & giáo trình"
        },
        "practice": {
            "status": practice_status,
            "percent": practice_percent,
            "message": "Tạo câu hỏi trắc nghiệm & Flashcard"
        },
        "schedule": {
            "status": schedule_status,
            "percent": schedule_percent,
            "message": "Tối ưu hóa lịch học cá nhân"
        }
    }
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE course_syllabi
               SET parsed_json = COALESCE(parsed_json, '{}'::jsonb) || $3::jsonb
               WHERE subject_id=$1 AND user_id=$2""",
            course_id,
            user_id,
            {"progress": progress_data},
        )


async def update_syllabus_progress(
    pool: asyncpg.Pool,
    course_id: str,
    user_id: str,
    stage: str,
    message: str,
    percent: int,
    detail: str | None = None,
) -> None:
    overall_percent = round(percent * 0.4)
    await update_onboarding_progress(
        pool, course_id, user_id,
        stage=stage, percent=overall_percent, message=message,
        syllabus_status="processing", syllabus_percent=percent,
        practice_status="pending", practice_percent=0,
        schedule_status="pending", schedule_percent=0,
        detail=detail
    )


async def mark_syllabus_failed(pool: asyncpg.Pool, course_id: str, user_id: str, error: Exception | str) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE course_syllabi
               SET status='failed', parsed_json=COALESCE(parsed_json, '{}'::jsonb) || $3::jsonb
               WHERE subject_id=$1 AND user_id=$2""",
            course_id,
            user_id,
            {
                "error": str(error),
                "progress": {
                    "stage": "failed",
                    "percent": 100,
                    "message": "Thiết lập thất bại",
                    "detail": str(error),
                    "syllabus": {"status": "failed", "percent": 100, "message": "Thất bại"},
                    "practice": {"status": "failed", "percent": 0, "message": "Thất bại"},
                    "schedule": {"status": "failed", "percent": 0, "message": "Thất bại"},
                },
            },
        )


async def batch_generate_practice_materials(
    pool: asyncpg.Pool,
    course_id: str,
    user_id: str,
) -> None:
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM topics WHERE subject_id=$1 AND user_id=$2 ORDER BY order_idx", course_id, user_id)
    topics = [_topic_from_row(row) for row in rows]
    if not topics:
        return

    chunks = await list_chunks(pool, course_id, user_id)
    batch_size = 1
    total_topics = len(topics)
    completed_topics = 0

    for i in range(0, total_topics, batch_size):
        batch_topics = topics[i : i + batch_size]
        batch_chunks = []
        for topic in batch_topics:
            topic_chunks = [c for c in chunks if topic["id"] in (c.get("topicIds") or [])]
            batch_chunks.extend(topic_chunks[:4])

        context_str = _rag_context(batch_chunks) if batch_chunks else "No detailed text context. Use topic title and description."
        
        topics_prompt = "\n".join([
            f"- Topic ID: {t['id']}\n  Title: {t['title']}\n  Description: {t['description']}"
            for t in batch_topics
        ])

        system_prompt = "You are an expert educator. Generate quizzes for the listed topics. Respond only with structured JSON."
        user_prompt = f"""
Course: {batch_topics[0]['courseId']}
Topics:
{topics_prompt}

Context:
{context_str}

For EACH topic listed above, generate exactly 3 multiple-choice questions. Each question must have:
- "topicId": matching the exact Topic ID.
- "question": clear question text.
- "options": exactly 4 options.
- "correctAnswer": must exactly match one of the options.
- "explanation": brief explanation.

Return a JSON object containing "quizzes" (array of questions).
Return exactly this JSON structure:
{{
  "quizzes": [
    {{
      "topicId": "topic-id-1",
      "question": "...",
      "options": ["A", "B", "C", "D"],
      "correctAnswer": "A",
      "explanation": "..."
    }}
  ]
}}
"""
        try:
            res = await _run_blocking(complete_json, system_prompt, user_prompt, 0.2)
            if not isinstance(res, dict):
                res = {}
        except Exception as e:
            logger.error(f"Error calling LLM for batch practice generation: {e}")
            res = {}

        quizzes_list = res.get("quizzes", []) if isinstance(res, dict) else []

        course_dict = await get_course(pool, course_id, user_id)

        for topic in batch_topics:
            topic_quizzes = [q for q in quizzes_list if isinstance(q, dict) and q.get("topicId") == topic["id"]]

            topic_chunks = [c for c in chunks if topic["id"] in (c.get("topicIds") or [])]

            if not topic_quizzes:
                topic_quizzes = _fallback_quiz_questions(course_dict, topic_chunks, 3, topic["id"])
                for q in topic_quizzes:
                    q["topicId"] = topic["id"]
            else:
                topic_quizzes = _normalize_quiz_questions(course_dict, topic_chunks, topic_quizzes, [], len(topic_quizzes), topic["id"])

            # Derive flashcards from the quizzes to make sure they are exactly the same
            topic_flash = []
            for q in topic_quizzes:
                topic_flash.append({
                    "topicId": topic["id"],
                    "front": q["question"],
                    "back": q["correctAnswer"],
                    "explanation": q["explanation"]
                })

            quiz_id = f"quiz_{uuid.uuid4().hex[:10]}"
            async with pool.acquire() as conn:
                await conn.execute(
                    """INSERT INTO practice_quizzes (id, subject_id, user_id, topic_id, title, difficulty, instructions, questions)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8)""",
                    quiz_id,
                    course_id,
                    user_id,
                    topic["id"],
                    f"Practice quiz: {topic['title']}",
                    "medium",
                    "",
                    topic_quizzes,
                )

                for card in topic_flash:
                    card_id = f"flashcard_{uuid.uuid4().hex[:10]}"
                    await conn.execute(
                        """INSERT INTO flashcards (id, subject_id, user_id, topic_id, front, back, explanation, due_at)
                           VALUES ($1,$2,$3,$4,$5,$6,$7,now())""",
                        card_id,
                        course_id,
                        user_id,
                        topic["id"],
                        card["front"],
                        card["back"],
                        card.get("explanation") or "",
                    )

            completed_topics += 1
            practice_percent = round((completed_topics / total_topics) * 100)
            await update_onboarding_progress(
                pool, course_id, user_id,
                stage="generating_practice", percent=round(70 + practice_percent * 0.3),
                message=f"Đang tạo câu hỏi luyện tập và flashcard cho '{topic['title']}' ({completed_topics}/{total_topics})...",
                syllabus_status="completed", syllabus_percent=100,
                practice_status="generating", practice_percent=practice_percent,
                schedule_status="completed", schedule_percent=100
            )


async def process_syllabus_file(pool: asyncpg.Pool, course_id: str, storage_path: str, payload: dict[str, Any], user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
    try:
        await update_syllabus_progress(pool, course_id, user_id, "extracting_text", "Đang đọc nội dung file syllabus...", 30)
        text = await asyncio.to_thread(lambda: sanitize_text_for_postgres(extract_text_from_file_path(storage_path)))
        async with pool.acquire() as conn:
            await conn.execute(
                """UPDATE course_syllabi
                   SET raw_text=$3, parsed_json=COALESCE(parsed_json, '{}'::jsonb) || $4::jsonb
                   WHERE subject_id=$1 AND user_id=$2""",
                course_id,
                user_id,
                text,
                {"filename": payload.get("filename"), "storagePath": payload.get("storagePath")},
            )
        await update_syllabus_progress(pool, course_id, user_id, "parsing_lessons", "Đang tách timeline và bài học...", 65, f"{len(text)} ký tự")
        return await create_syllabus(pool, course_id, {**payload, "mode": "upload", "text": text}, user_id, status="review_pending")
    except Exception as exc:
        await mark_syllabus_failed(pool, course_id, user_id, exc)
        raise
    finally:
        if storage_path and os.path.exists(storage_path):
            try:
                os.remove(storage_path)
            except Exception:
                pass


async def process_onboarding_course(
    pool: asyncpg.Pool,
    course_id: str,
    user_id: str,
    syllabus_storage_path: str,
    syllabus_payload: dict[str, Any],
    source_ids: list[str],
    plan_payload: dict[str, Any],
) -> None:
    try:
        # 1. Initialize progress
        await update_onboarding_progress(
            pool, course_id, user_id,
            stage="extracting_text", percent=5, message="Đang khởi tạo thiết lập...",
            syllabus_status="processing", syllabus_percent=5,
            practice_status="pending", practice_percent=0,
            schedule_status="pending", schedule_percent=0
        )

        # 2. Syllabus processing
        await process_syllabus_file(pool, course_id, syllabus_storage_path, syllabus_payload, user_id)

        # 3. Sources processing
        total_sources = len(source_ids)
        for index, source_id in enumerate(source_ids):
            await update_onboarding_progress(
                pool, course_id, user_id,
                stage="processing_sources", percent=round(10 + (index / total_sources) * 20),
                message=f"Đang xử lý tài liệu học tập {index + 1}/{total_sources}...",
                syllabus_status="processing", syllabus_percent=round(10 + (index / total_sources) * 20),
                practice_status="pending", practice_percent=0,
                schedule_status="pending", schedule_percent=0
            )
            try:
                await process_source_file(pool, source_id, user_id)
            except Exception:
                logger.exception("Onboarding source processing failed", extra={"courseId": course_id, "sourceId": source_id, "userId": user_id})
                continue

        # 4. Map syllabus - SKIP in Phase 1
        # Instead of running map_syllabus, generate_plan, batch_generate_practice_materials:
        await update_onboarding_progress(
            pool, course_id, user_id,
            stage="review_pending", percent=35, message="Đang chờ bạn phê duyệt cấu trúc bài học giáo trình...",
            syllabus_status="review_pending", syllabus_percent=100,
            practice_status="pending", practice_percent=0,
            schedule_status="pending", schedule_percent=0
        )
        return
    except Exception as exc:
        logger.exception("Onboarding course processing failed", extra={"courseId": course_id, "userId": user_id})
        await mark_syllabus_failed(pool, course_id, user_id, exc)


async def approve_syllabus(
    pool: asyncpg.Pool,
    course_id: str,
    lessons_payload: list[dict[str, Any]],
    plan_payload: dict[str, Any],
    user_id: str = DEFAULT_USER_ID,
    background_tasks: BackgroundTasks | None = None,
    generate_quizzes: bool = True,
) -> dict[str, Any]:
    import time
    t0 = time.perf_counter()
    chapters = _chapters_from_lessons(lessons_payload)
    
    t_db_start = time.perf_counter()
    async with pool.acquire() as conn:
        syllabus_row = await conn.fetchrow(
            "SELECT id, raw_text, parsed_json FROM course_syllabi WHERE subject_id=$1 AND user_id=$2 ORDER BY created_at DESC LIMIT 1",
            course_id, user_id
        )
        if not syllabus_row:
            raise KeyError("Syllabus not found")
        syllabus_id = syllabus_row["id"]
        parsed = _json_value(syllabus_row["parsed_json"], {})
        parsed["lessons"] = lessons_payload
        parsed["normalizedLessons"] = lessons_payload
        parsed["chapters"] = chapters
 
        async with conn.transaction():
            await conn.execute(
                "UPDATE course_syllabi SET status='ready', parsed_json=$3::jsonb WHERE id=$1 AND user_id=$2",
                syllabus_id, user_id, parsed
            )
            await conn.execute("DELETE FROM syllabus_lessons WHERE subject_id=$1", course_id)
            await conn.execute("DELETE FROM study_tasks WHERE subject_id=$1 AND user_id=$2 AND status <> 'done'", course_id, user_id)
            
            for index, lesson in enumerate(lessons_payload):
                lesson_id = f"lesson_{uuid.uuid4().hex[:10]}"
                await conn.execute(
                    """INSERT INTO syllabus_lessons (id, syllabus_id, subject_id, week_number, lesson_number, title,
                       description, assigned_readings, starts_on, ends_on, status, order_idx)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)""",
                    lesson_id, syllabus_id, course_id, _int_or_none(lesson.get("week_number") or lesson.get("weekNumber")),
                    _int_or_none(lesson.get("lesson_number") or lesson.get("lessonNumber")),
                    lesson.get("title") or f"Lesson {index + 1}", lesson.get("description") or "",
                    lesson.get("assigned_readings") or lesson.get("assignedReadings") or [],
                    _parse_date(lesson.get("startsOn") or lesson.get("starts_on")),
                    _parse_date(lesson.get("endsOn") or lesson.get("ends_on")),
                    "future", index,
                )
            # Mark onboarding as processing so the UI can poll for completion
            progress_data = {
                "stage": "processing",
                "percent": 40,
                "message": "Đang lập lịch và tạo tài liệu học tập...",
                "syllabus": {
                    "status": "completed",
                    "percent": 100,
                    "message": "Trích xuất tài liệu & giáo trình"
                },
                "practice": {
                    "status": "processing",
                    "percent": 0,
                    "message": "Tạo câu hỏi trắc nghiệm & Flashcard"
                },
                "schedule": {
                    "status": "processing",
                    "percent": 0,
                    "message": "Tối ưu hóa lịch học cá nhân"
                }
            }
            await conn.execute(
                """UPDATE course_syllabi
                   SET parsed_json = COALESCE(parsed_json, '{}'::jsonb) || $3::jsonb
                   WHERE subject_id=$1 AND user_id=$2""",
                course_id,
                user_id,
                {"progress": progress_data},
            )
    t_db = time.perf_counter() - t_db_start
    logger.info(f"[PROFILE] DB transaction and lesson inserts took {t_db:.4f}s")
    # --- Heavy work: run in background so HTTP response returns immediately ---
    async def _post_approve_background() -> None:
        try:
            await map_syllabus(pool, course_id, user_id)
            logger.info("[BG] map_syllabus done")
        except Exception:
            logger.exception("[BG] map_syllabus failed")

        try:
            await generate_plan(pool, course_id, plan_payload, user_id)
            logger.info("[BG] generate_plan done")
        except Exception:
            logger.exception("[BG] generate_plan failed")
            await repository.set_plan_dirty(pool, user_id, True)

        if generate_quizzes:
            try:
                await batch_generate_practice_materials(pool, course_id, user_id)
                logger.info("[BG] batch_generate_practice_materials done")
            except Exception:
                logger.exception("[BG] batch_generate_practice_materials failed")

        try:
            await update_onboarding_progress(
                pool, course_id, user_id,
                stage="completed", percent=100, message="Đã hoàn thành thiết lập môn học!",
                syllabus_status="completed", syllabus_percent=100,
                practice_status="completed", practice_percent=100,
                schedule_status="completed", schedule_percent=100,
            )
        except Exception:
            logger.exception("[BG] update_onboarding_progress failed")

    if background_tasks is not None:
        background_tasks.add_task(_post_approve_background)
    else:
        # Fallback for non-HTTP callers (tests, scripts)
        await _post_approve_background()

    total_time = time.perf_counter() - t0
    logger.info(f"[PROFILE] approve_syllabus (DB only) took {total_time:.4f}s — heavy work queued to background")
    return {
        "status": "success",
        "course": await get_course(pool, course_id, user_id),
        "profile": {
            "db_took_seconds": t_db,
            "total_took_seconds": total_time,
            "background_tasks_queued": background_tasks is not None,
        },
    }


async def get_syllabus(pool: asyncpg.Pool, course_id: str, user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
    await _require_course(pool, course_id, user_id)
    await _repair_syllabus_mapping_if_needed(pool, course_id, user_id)
    async with pool.acquire() as conn:
        syllabus = await conn.fetchrow("SELECT * FROM course_syllabi WHERE subject_id=$1 AND user_id=$2 ORDER BY created_at DESC LIMIT 1", course_id, user_id)
        lessons = await conn.fetch("SELECT * FROM syllabus_lessons WHERE subject_id=$1 ORDER BY order_idx, lesson_number NULLS LAST", course_id)
        mappings = await conn.fetch(
            """SELECT lesson_id, COUNT(DISTINCT topic_id) AS topic_count, COUNT(DISTINCT chunk_id) AS chunk_count
               FROM lesson_material_mappings WHERE lesson_id = ANY($1::text[]) GROUP BY lesson_id""",
            [row["id"] for row in lessons] or [""],
        )
    lesson_items = [_lesson_from_row(row) for row in lessons]
    mapping_by_lesson = {row["lesson_id"]: {"topicCount": row["topic_count"], "chunkCount": row["chunk_count"]} for row in mappings}
    current = next((lesson for lesson in lesson_items if syllabus and lesson["id"] == syllabus["current_lesson_id"]), None)
    return {
        "courseId": course_id,
        "syllabus": _syllabus_from_row(syllabus) if syllabus else None,
        "lessons": [{**lesson, "mapping": mapping_by_lesson.get(lesson["id"], {"topicCount": 0, "chunkCount": 0})} for lesson in lesson_items],
        "currentLesson": current,
        "mappingSummary": {
            "lessonCount": len(lesson_items),
            "mappedLessons": sum(1 for lesson in lesson_items if mapping_by_lesson.get(lesson["id"], {}).get("topicCount", 0) > 0),
            "unmappedLessons": sum(1 for lesson in lesson_items if mapping_by_lesson.get(lesson["id"], {}).get("topicCount", 0) == 0),
        },
    }


async def update_current_lesson(pool: asyncpg.Pool, course_id: str, payload: dict[str, Any], user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
    await _require_course(pool, course_id, user_id)
    lesson_id = payload.get("lessonId") or payload.get("lesson_id")
    week_number = _int_or_none(payload.get("weekNumber") or payload.get("week_number"))
    lesson_number = _int_or_none(payload.get("lessonNumber") or payload.get("lesson_number"))
    async with pool.acquire() as conn:
        if not lesson_id:
            row = await conn.fetchrow(
                """SELECT id FROM syllabus_lessons WHERE subject_id=$1
                   AND ($2::int IS NULL OR week_number=$2) AND ($3::int IS NULL OR lesson_number=$3)
                   ORDER BY order_idx LIMIT 1""",
                course_id, week_number, lesson_number,
            )
            lesson_id = row["id"] if row else None
        target = await conn.fetchrow("SELECT * FROM syllabus_lessons WHERE id=$1 AND subject_id=$2", lesson_id, course_id) if lesson_id else None
        if not target:
            raise ValueError("Matching lesson not found")
        async with conn.transaction():
            await conn.execute(
                """UPDATE syllabus_lessons SET status = CASE
                   WHEN order_idx < $2 THEN 'taught'
                   WHEN order_idx = $2 THEN 'current'
                   ELSE 'future' END
                   WHERE subject_id=$1""",
                course_id, target["order_idx"],
            )
            await conn.execute(
                "UPDATE course_syllabi SET current_lesson_id=$2, current_week=$3, join_position='mid_semester' WHERE subject_id=$1 AND user_id=$4",
                course_id, lesson_id, target["week_number"], user_id,
            )
    await _sync_topic_learning_states(pool, course_id, user_id)
    await repository.set_plan_dirty(pool, user_id, True)
    return await get_syllabus(pool, course_id, user_id)


async def _lesson_topic_mapping_counts(conn: asyncpg.Connection, lesson_ids: list[str]) -> dict[str, int]:
    if not lesson_ids:
        return {}
    rows = await conn.fetch(
        """SELECT lesson_id, COUNT(DISTINCT topic_id) AS topic_count
           FROM lesson_material_mappings
           WHERE lesson_id = ANY($1::text[])
           GROUP BY lesson_id""",
        lesson_ids,
    )
    return {row["lesson_id"]: int(row["topic_count"] or 0) for row in rows}


async def _rebuild_syllabus_mappings(
    conn: asyncpg.Connection,
    course_id: str,
    user_id: str,
    lessons: list[asyncpg.Record],
    chunks: list[asyncpg.Record],
) -> None:
    await _sync_chapter_topics_from_syllabus(conn, course_id, user_id, lessons)
    await conn.execute(
        """DELETE FROM topics
           WHERE subject_id=$1 AND user_id=$2 AND id NOT LIKE $3 AND id NOT LIKE $4""",
        course_id, user_id, f"topic-{course_id}-syllabus-%", f"topic-{course_id}-chapter-%",
    )
    await conn.execute(
        "UPDATE document_chunks SET topic_ids=ARRAY[]::text[] WHERE subject_id=$1 AND user_id=$2",
        course_id, user_id,
    )
    await conn.execute(
        "UPDATE course_sources SET topic_count=0 WHERE subject_id=$1 AND user_id=$2",
        course_id, user_id,
    )
    topics = await conn.fetch("SELECT * FROM topics WHERE subject_id=$1 AND user_id=$2 ORDER BY order_idx", course_id, user_id)
    topic_ids_by_lesson: dict[str, list[str]] = {}
    for topic in topics:
        if topic["lesson_id"]:
            topic_ids_by_lesson.setdefault(topic["lesson_id"], []).append(topic["id"])
    await conn.execute("DELETE FROM lesson_material_mappings WHERE lesson_id = ANY($1::text[])", [row["id"] for row in lessons] or [""])
    for topic in topics:
        if topic["lesson_id"]:
            await conn.execute(
                """INSERT INTO lesson_material_mappings (id, lesson_id, topic_id, confidence, reason)
                   VALUES ($1,$2,$3,$4,$5)""",
                f"map_{uuid.uuid4().hex[:10]}", topic["lesson_id"], topic["id"], 1.0, "Canonical syllabus topic for this lesson.",
            )
    for chunk in chunks:
        lesson, confidence, reason = _best_lesson_match(lessons, f"{chunk['filename']} {chunk['section_path']} {chunk['section_title']} {chunk['quote']} {chunk['text'][:1200]}")
        if lesson and confidence >= 0.12:
            await conn.execute(
                """INSERT INTO lesson_material_mappings (id, lesson_id, source_id, chunk_id, confidence, reason)
                   VALUES ($1,$2,$3,$4,$5,$6)""",
                f"map_{uuid.uuid4().hex[:10]}", lesson["id"], chunk["source_id"], chunk["id"], confidence, reason,
            )
            await conn.execute(
                "UPDATE document_chunks SET topic_ids=$2 WHERE id=$1 AND user_id=$3",
                chunk["id"], topic_ids_by_lesson.get(lesson["id"], []), user_id,
            )


async def _repair_syllabus_mapping_if_needed(
    pool: asyncpg.Pool,
    course_id: str,
    user_id: str,
    *,
    force: bool = False,
) -> bool:
    remapped = False
    async with pool.acquire() as conn:
        async with conn.transaction():
            syllabus = await conn.fetchrow(
                """SELECT id, status FROM course_syllabi
                   WHERE subject_id=$1 AND user_id=$2
                   ORDER BY created_at DESC LIMIT 1""",
                course_id,
                user_id,
            )
            if not syllabus or syllabus["status"] == "skipped":
                return False
            if not force and syllabus["status"] in {"processing", "failed", "review_pending"}:
                return False

            await _repair_syllabus_lessons_from_parsed(conn, course_id, user_id)
            lessons = await conn.fetch("SELECT * FROM syllabus_lessons WHERE subject_id=$1 ORDER BY order_idx", course_id)
            if not lessons:
                return False

            lesson_ids = [row["id"] for row in lessons]
            mapping_counts = await _lesson_topic_mapping_counts(conn, lesson_ids)
            needs_repair = force or not any(mapping_counts.values())
            if not needs_repair:
                return False

            chunks = await conn.fetch("SELECT * FROM document_chunks WHERE subject_id=$1 AND user_id=$2 ORDER BY chunk_index", course_id, user_id)
            await _rebuild_syllabus_mappings(conn, course_id, user_id, lessons, chunks)
            remapped = True

    if remapped:
        await _sync_topic_learning_states(pool, course_id, user_id)
        await repository.set_plan_dirty(pool, user_id, True)
    return remapped


async def map_syllabus(pool: asyncpg.Pool, course_id: str, user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
    await _require_course(pool, course_id, user_id)
    await _repair_syllabus_mapping_if_needed(pool, course_id, user_id, force=True)
    syllabus = await get_syllabus(pool, course_id, user_id)
    return {"status": "success", **syllabus}


async def generate_diagnostic_test(pool: asyncpg.Pool, course_id: str, payload: dict[str, Any] | None = None, user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
    allowed_topic_ids = await _allowed_topic_ids(pool, course_id, user_id, include_current=True)
    if not allowed_topic_ids:
        raise ValueError("No taught or current syllabus topics are available for diagnostics")
    query = " ".join(await _topic_titles(pool, allowed_topic_ids))
    return await generate_quiz(pool, {
        "courseId": course_id,
        "topicIds": allowed_topic_ids,
        "query": query or "diagnostic review",
        "count": int((payload or {}).get("count") or 5),
        "title": "Diagnostic check: taught lessons",
        "instructions": "Short diagnostic for topics already taught according to the syllabus.",
    }, user_id)


async def process_source(pool: asyncpg.Pool, source_id: str, user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
    async with pool.acquire() as conn:
        source_row = await conn.fetchrow("SELECT * FROM course_sources WHERE id=$1 AND user_id=$2", source_id, user_id)
    if not source_row:
        raise KeyError("Source not found")
    source = _source_from_row(source_row)
    try:
        prepared = await _prepare_source_index(pool, source_row, user_id)
        chunks = prepared["chunks"]
        topics = prepared["topics"]
        await _replace_chunks_and_topics(pool, source, chunks, topics, user_id, replace_source_topics=True)
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE course_sources SET status='ready', parsed_at=now(), topic_count=$3, error_message=NULL WHERE id=$1 AND user_id=$2",
                source_id,
                user_id,
                len(topics),
            )
        await map_syllabus(pool, source["courseId"], user_id)
        return {"source": await get_source(pool, source_id, user_id), "chunks": chunks, "topics": await list_topics(pool, source["courseId"], user_id)}
    except Exception as exc:
        async with pool.acquire() as conn:
            await conn.execute("UPDATE course_sources SET status='failed', error_message=$3 WHERE id=$1 AND user_id=$2", source_id, user_id, str(exc))
        raise

async def reindex_course_topics(pool: asyncpg.Pool, course_id: str, user_id: str = DEFAULT_USER_ID, apply: bool = False) -> dict[str, Any]:
    await _require_course(pool, course_id, user_id)
    async with pool.acquire() as conn:
        source_rows = await conn.fetch(
            "SELECT * FROM course_sources WHERE subject_id=$1 AND user_id=$2 ORDER BY created_at, id",
            course_id,
            user_id,
        )
    prepared = []
    existing_count = 0
    for row in source_rows:
        item = await _prepare_source_index(pool, row, user_id, existing_count)
        prepared.append(item)
        existing_count += len(item["topics"])

    summary = {
        "courseId": course_id,
        "apply": apply,
        "sourceCount": len(prepared),
        "chunkCount": sum(len(item["chunks"]) for item in prepared),
        "topicCount": sum(len(item["topics"]) for item in prepared),
        "sources": [
            {
                "sourceId": item["source"]["id"],
                "filename": item["source"].get("filename"),
                "pages": len(item["pages"]),
                "sections": len(item["sections"]),
                "chunks": len(item["chunks"]),
                "topics": len(item["topics"]),
                "topicTitles": [topic["title"] for topic in item["topics"][:12]],
            }
            for item in prepared
        ],
    }
    if not apply:
        return summary

    await _replace_course_index(pool, course_id, user_id, prepared)
    await map_syllabus(pool, course_id, user_id)
    await _auto_rebuild_course_plan(pool, course_id, user_id)
    return {**summary, "topics": await list_topics(pool, course_id, user_id)}

async def _prepare_source_index(pool: asyncpg.Pool, source_row: asyncpg.Record, user_id: str, existing_count: int | None = None) -> dict[str, Any]:
    source = _source_from_row(source_row)
    text = source_row["text_content"] or ""
    pages = parse_pages(text)
    sections = build_sections(source["id"], pages)
    chunks = create_chunks(source["courseId"], source, sections)
    topics: list[dict[str, Any]] = []
    return {"source": source, "pages": pages, "sections": sections, "chunks": chunks, "topics": topics}

def _apply_subtopic_defaults(topic: dict[str, Any], course_id: str, source_id: str | None = None, index: int = 0) -> None:
    title = str(topic.get("title") or f"Subtopic {index + 1}").strip()
    if source_id:
        key = hashlib.sha1(f"{source_id}:{title.lower()}:{index}".encode()).hexdigest()[:10]
        topic["id"] = f"topic-{course_id}-{source_id}-{key}"
    parent_title = _parent_topic_title(topic)
    topic.setdefault("parent_topic_id", _parent_topic_id(course_id, parent_title))
    topic.setdefault("parent_topic_title", parent_title)
    topic.setdefault("is_subtopic", True)
    topic.setdefault("learning_state", "taught")
    topic.setdefault("practice_allowed", True)

def _parent_topic_title(topic: dict[str, Any]) -> str:
    return str(
        topic.get("chapter_title")
        or topic.get("chapterTitle")
        or topic.get("section_path")
        or topic.get("sectionPath")
        or topic.get("title")
        or "Course topics"
    ).strip()[:120]

def _parent_topic_id(course_id: str, title: str) -> str:
    key = hashlib.sha1(f"{course_id}:{title.lower()}".encode()).hexdigest()[:10]
    return f"parent-{course_id}-{key}"


async def list_topics(pool: asyncpg.Pool, course_id: str, user_id: str = DEFAULT_USER_ID) -> list[dict[str, Any]]:
    await _repair_syllabus_mapping_if_needed(pool, course_id, user_id)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT t.*, sl.title AS lesson_title,
                      COUNT(*) OVER (PARTITION BY COALESCE(t.parent_topic_id, t.id)) AS parent_subtopic_count,
                      SUM(CASE WHEN t.practice_allowed THEN 1 ELSE 0 END) OVER (PARTITION BY COALESCE(t.parent_topic_id, t.id)) AS parent_available_count,
                      AVG(t.mastery) OVER (PARTITION BY COALESCE(t.parent_topic_id, t.id)) AS parent_mastery_avg,
                      AVG(t.mastery) FILTER (WHERE t.practice_allowed) OVER (PARTITION BY COALESCE(t.parent_topic_id, t.id)) AS parent_available_mastery_avg,
                      (SELECT COUNT(*)::int FROM mastery_events me WHERE me.topic_id = t.id) AS review_count,
                      (SELECT COUNT(*)::int FROM practice_quizzes pq WHERE pq.topic_id = t.id) AS quiz_count,
                      (SELECT COUNT(*)::int FROM flashcards f WHERE f.topic_id = t.id) AS flashcard_count
               FROM topics t LEFT JOIN syllabus_lessons sl ON sl.id=t.lesson_id
               WHERE t.subject_id=$1 AND t.user_id=$2 ORDER BY t.order_idx, t.created_at""",
            course_id, user_id,
        )
    return [_topic_from_row(row) for row in rows]

async def submit_self_assessment(pool: asyncpg.Pool, course_id: str, payload: dict[str, Any], user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
    await _require_course(pool, course_id, user_id)
    await _sync_topic_learning_states(pool, course_id, user_id)
    ratings = payload.get("ratings") or []
    if not isinstance(ratings, list) or not ratings:
        raise ValueError("ratings is required")

    accepted: list[dict[str, Any]] = []
    for item in ratings:
        topic_id = str((item or {}).get("topicId") or (item or {}).get("topic_id") or "").strip()
        try:
            score = float((item or {}).get("score"))
        except (TypeError, ValueError):
            raise ValueError("score must be 0..10")
        if not topic_id or score < 0 or score > 10:
            raise ValueError("score must be 0..10")

        topic = await repository.get_topic(pool, topic_id)
        if not topic or topic.subject_id != course_id or topic.user_id != user_id:
            raise ValueError("Topic does not belong to this course")
        if topic.learning_state not in {"taught", "current"} or not topic.practice_allowed:
            raise ValueError("Future syllabus topics are locked")

        update = apply_self_assessment_seed(topic, score)
        await repository.update_topic(pool, topic)
        accepted.append({"topicId": topic.id, "masteryPercent": round(update["mastery"] * 100), "confidencePercent": round(topic.mastery_confidence * 100)})

    await repository.set_plan_dirty(pool, user_id, True)
    return {"accepted": accepted, "topics": await list_topics(pool, course_id, user_id), "course": await get_course(pool, course_id, user_id)}


async def generate_topic_map(pool: asyncpg.Pool, course_id: str, user_id: str = DEFAULT_USER_ID) -> list[dict[str, Any]]:
    topics = await list_topics(pool, course_id, user_id)
    if topics:
        await map_syllabus(pool, course_id, user_id)
    await map_syllabus(pool, course_id, user_id)
    return await list_topics(pool, course_id, user_id)


async def generate_plan(pool: asyncpg.Pool, course_id: str, payload: dict[str, Any], user_id: str = DEFAULT_USER_ID) -> list[dict[str, Any]]:
    await _require_course(pool, course_id, user_id)
    await generate_topic_map(pool, course_id, user_id)
    await _unlock_topics_without_sources(pool, course_id, user_id)

    updates: dict[str, Any] = {}
    if "availabilityWindows" in payload:
        windows = _normalize_availability_windows(payload.get("availabilityWindows"))
        updates["availability_windows"] = windows
        updates["days_available"] = _availability_window_days(windows)
    elif "availability" in payload:
        updates["days_available"] = _normalize_availability(payload.get("availability"))
    if payload.get("sessionMinutes") not in (None, ""):
        minutes = max(5, min(120, int(payload.get("sessionMinutes") or 30)))
        async with pool.acquire() as conn:
            await conn.execute("UPDATE topics SET cost_mins=$3 WHERE subject_id=$1 AND user_id=$2", course_id, user_id, minutes)
        updates["daily_goal_minutes"] = max(30, minutes)
    if updates:
        await repository.update_subject(pool, course_id, **updates)
    await repository.set_plan_dirty(pool, user_id, True)
    from app.services.unified_scheduler import build_subject_schedule
    await build_subject_schedule(
        pool,
        user_id,
        course_id,
        _parse_date(payload.get("startDate")) or date.today(),
        str(payload["preferredStartTime"]) if payload.get("preferredStartTime") else None,
    )
    return await list_tasks(pool, {"courseId": course_id}, user_id)


async def _unlock_topics_without_sources(pool: asyncpg.Pool, course_id: str, user_id: str) -> None:
    async with pool.acquire() as conn:
        source_count = await conn.fetchval(
            "SELECT COUNT(*) FROM course_sources WHERE subject_id=$1 AND user_id=$2",
            course_id,
            user_id,
        )
        if int(source_count or 0) == 0:
            return


async def _auto_generate_initial_plan(pool: asyncpg.Pool, course_id: str, payload: dict[str, Any], user_id: str) -> None:
    try:
        await generate_plan(pool, course_id, payload, user_id)
    except Exception:
        await repository.set_plan_dirty(pool, user_id, True)


async def _auto_rebuild_course_plan(pool: asyncpg.Pool, course_id: str, user_id: str) -> None:
    try:
        await repository.set_plan_dirty(pool, user_id, True)
        from app.services.unified_scheduler import build_subject_schedule
        await build_subject_schedule(pool, user_id, course_id, date.today())
    except Exception:
        await repository.set_plan_dirty(pool, user_id, True)


async def list_tasks(pool: asyncpg.Pool, params: dict[str, Any], user_id: str = DEFAULT_USER_ID) -> list[dict[str, Any]]:
    await ensure_dev_user(pool, user_id)
    
    # Trigger missed task status update
    from app.services.unified_scheduler import ensure_missed_tasks_marked
    try:
        await ensure_missed_tasks_marked(pool, user_id, date.today())
    except Exception as e:
        print(f"[list_tasks] Error marking missed tasks: {e}")
        
    if params.get("courseId"):
        await _repair_syllabus_mapping_if_needed(pool, params["courseId"], user_id)
    await _ensure_schedule_current_for_read(pool, user_id, params.get("courseId"))
    query = """SELECT st.*, s.name AS subject_name, sl.title AS mapped_lesson_title,
                      topic_stats.topic_stats, scope_items.scope_items
               FROM study_tasks st
               JOIN subjects s ON s.id=st.subject_id
               LEFT JOIN syllabus_lessons sl ON sl.id=st.lesson_id
               LEFT JOIN LATERAL (
                 SELECT jsonb_build_object(
                   'id', p.id,
                   'title', p.title,
                   'masteryPercent', ROUND(COALESCE(p.mastery, 0) * 100),
                   'confidencePercent', ROUND(COALESCE(p.mastery_confidence, 0) * 100),
                   'learningState', p.learning_state,
                   'practiceAllowed', p.practice_allowed,
                   'totalSubtopicCount', COALESCE(child_stats.total_count, 0),
                   'availableSubtopicCount', COALESCE(child_stats.available_count, 0),
                   'overallMasteryPercent', ROUND(COALESCE(child_stats.overall_mastery, p.mastery, 0) * 100),
                   'availableMasteryPercent',
                     CASE
                       WHEN child_stats.available_mastery IS NULL THEN NULL
                       ELSE ROUND(child_stats.available_mastery * 100)
                     END,
                   'scope', CASE
                     WHEN COALESCE(child_stats.total_count, 0) > 0
                      AND COALESCE(child_stats.available_count, 0) < COALESCE(child_stats.total_count, 0)
                     THEN 'partial_topic'
                     WHEN COALESCE(child_stats.total_count, 0) > 0
                     THEN 'topic'
                     ELSE COALESCE(st.scope, 'topic')
                   END
                 ) AS topic_stats
                 FROM topics p
                 LEFT JOIN LATERAL (
                   SELECT COUNT(*)::int AS total_count,
                          COUNT(*) FILTER (
                            WHERE (
                              (csl.starts_on IS NOT NULL AND csl.starts_on <= st.scheduled_date)
                              OR (csl.starts_on IS NULL AND (c.practice_allowed=true OR c.learning_state IN ('taught','current')))
                            )
                          )::int AS available_count,
                          AVG(c.mastery) AS overall_mastery,
                          AVG(c.mastery) FILTER (
                            WHERE (
                              (csl.starts_on IS NOT NULL AND csl.starts_on <= st.scheduled_date)
                              OR (csl.starts_on IS NULL AND (c.practice_allowed=true OR c.learning_state IN ('taught','current')))
                            )
                          ) AS available_mastery
                   FROM topics c
                   LEFT JOIN syllabus_lessons csl ON csl.id=c.lesson_id
                   WHERE c.parent_topic_id=p.id AND c.is_subtopic=true
                 ) child_stats ON true
                 WHERE p.id=COALESCE(
                   (SELECT pp.id FROM topics pp WHERE pp.id=st.parent_topic_id AND pp.subject_id=st.subject_id LIMIT 1),
                   st.topic_id
                 )
                   AND p.subject_id=st.subject_id
                 LIMIT 1
               ) topic_stats ON true
               LEFT JOIN LATERAL (
                 SELECT COALESCE(
                   jsonb_agg(
                     jsonb_build_object(
                       'id', scoped.id,
                       'title', scoped.title,
                       'masteryPercent', ROUND(COALESCE(scoped.mastery, 0) * 100),
                       'confidencePercent', ROUND(COALESCE(scoped.mastery_confidence, 0) * 100),
                       'learningState', scoped.learning_state,
                       'practiceAllowed', scoped.practice_allowed,
                       'lessonId', scoped.lesson_id,
                       'startsOn', scoped.scoped_starts_on,
                       'endsOn', scoped.scoped_ends_on
                     )
                     ORDER BY scoped.order_idx, scoped.title
                   ),
                   '[]'::jsonb
                 ) AS scope_items
                 FROM (
                   SELECT c.*, csl.starts_on AS scoped_starts_on, csl.ends_on AS scoped_ends_on
                   FROM topics c
                   LEFT JOIN syllabus_lessons csl ON csl.id=c.lesson_id
                   WHERE c.parent_topic_id=COALESCE(
                       (SELECT pp.id FROM topics pp WHERE pp.id=st.parent_topic_id AND pp.subject_id=st.subject_id LIMIT 1),
                       st.topic_id
                     )
                     AND c.is_subtopic=true
                     AND (
                       (csl.starts_on IS NOT NULL AND csl.starts_on <= st.scheduled_date)
                       OR (csl.starts_on IS NULL AND (c.practice_allowed=true OR c.learning_state IN ('taught','current')))
                     )
                   UNION ALL
                   SELECT t.*, tsl.starts_on AS scoped_starts_on, tsl.ends_on AS scoped_ends_on
                   FROM topics t
                   LEFT JOIN syllabus_lessons tsl ON tsl.id=t.lesson_id
                   WHERE t.id=st.topic_id
                     AND NOT EXISTS (
                       SELECT 1
                       FROM topics c2
                       WHERE c2.parent_topic_id=COALESCE(
                           (SELECT pp.id FROM topics pp WHERE pp.id=st.parent_topic_id AND pp.subject_id=st.subject_id LIMIT 1),
                           st.topic_id
                         )
                         AND c2.is_subtopic=true
                     )
                 ) scoped
               ) scope_items ON true
               WHERE st.user_id=$1"""
    values: list[Any] = [user_id]
    if params.get("courseId"):
        values.append(params["courseId"])
        query += f" AND st.subject_id=${len(values)}"
    if params.get("status"):
        values.append(params["status"])
        query += f" AND st.status=${len(values)}"
    if params.get("start"):
        values.append(_parse_datetime(params["start"]))
        query += f" AND COALESCE(st.end_at, st.scheduled_date::timestamptz) >= ${len(values)}"
    if params.get("end"):
        values.append(_parse_datetime(params["end"]))
        query += f" AND COALESCE(st.start_at, st.scheduled_date::timestamptz) <= ${len(values)}"
    query += " ORDER BY COALESCE(st.start_at, st.scheduled_date::timestamptz), st.created_at"
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *values)
    return [_task_from_row(row) for row in rows]


async def _ensure_schedule_current_for_read(pool: asyncpg.Pool, user_id: str, course_id: str | None = None) -> None:
    dirty = await repository.is_plan_dirty(pool, user_id)
    if dirty:
        if course_id:
            from app.services.unified_scheduler import build_subject_schedule
            await build_subject_schedule(pool, user_id, course_id, date.today())
        else:
            from app.services.unified_scheduler import build_unified_schedule
            await build_unified_schedule(pool, user_id, date.today())



async def create_task(pool: asyncpg.Pool, payload: dict[str, Any], user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
    course_id = payload.get("courseId") or payload.get("subjectId")
    if not course_id:
        raise ValueError("courseId is required")
    await _require_course(pool, course_id, user_id)
    title = str(payload.get("title") or payload.get("topicTitle") or "Study task")
    start_at = _parse_datetime(payload.get("startAt")) or datetime.combine(date.today(), time(18, 0), tzinfo=timezone.utc)
    end_at = _parse_datetime(payload.get("endAt")) or start_at + timedelta(minutes=int(payload.get("durationMinutes") or 30))
    duration = int(payload.get("durationMinutes") or max(1, round((end_at - start_at).total_seconds() / 60)))
    task_id = str(payload.get("id") or f"task_{uuid.uuid4().hex[:10]}")
    topic_id = payload.get("topicId")
    async with pool.acquire() as conn:
        if topic_id:
            exists = await conn.fetchval("SELECT EXISTS(SELECT 1 FROM topics WHERE id=$1)", topic_id)
            if not exists:
                topic_id = None
        try:
            await conn.execute(
                """INSERT INTO study_tasks (id, subject_id, topic_id, user_id, topic_title, type, duration_minutes,
                                            reason, scheduled_date, status, day, title, start_at, end_at, priority,
                                            lesson_id, lesson_title, learning_state, subtopic_id, parent_topic_id,
                                            is_partial_topic, scope, earliest_allowed_at)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23)
                   ON CONFLICT (id) DO UPDATE SET title=EXCLUDED.title, start_at=EXCLUDED.start_at, end_at=EXCLUDED.end_at,
                       status=EXCLUDED.status, priority=EXCLUDED.priority""",
                task_id,
                course_id,
                topic_id,
                user_id,
                payload.get("topicTitle") or title,
                payload.get("type") or "review",
                duration,
                payload.get("reason") or "Created manually.",
                start_at.date(),
                payload.get("status") or "todo",
                start_at.strftime("%a"),
                title,
                start_at,
                end_at,
                payload.get("priority") or "medium",
                payload.get("lessonId"),
                payload.get("lessonTitle"),
                payload.get("learningState"),
                payload.get("subtopicId") or topic_id,
                payload.get("parentTopicId"),
                bool(payload.get("isPartialTopic", False)),
                payload.get("scope") or "subtopic",
                _parse_datetime(payload.get("earliestAllowedAt")),
            )
        except asyncpg.exceptions.ForeignKeyViolationError:
            # Fallback: retry insertion with None topic_id
            await conn.execute(
                """INSERT INTO study_tasks (id, subject_id, topic_id, user_id, topic_title, type, duration_minutes,
                                            reason, scheduled_date, status, day, title, start_at, end_at, priority,
                                            lesson_id, lesson_title, learning_state, subtopic_id, parent_topic_id,
                                            is_partial_topic, scope, earliest_allowed_at)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23)
                   ON CONFLICT (id) DO UPDATE SET title=EXCLUDED.title, start_at=EXCLUDED.start_at, end_at=EXCLUDED.end_at,
                       status=EXCLUDED.status, priority=EXCLUDED.priority""",
                task_id,
                course_id,
                None,
                user_id,
                payload.get("topicTitle") or title,
                payload.get("type") or "review",
                duration,
                payload.get("reason") or "Created manually.",
                start_at.date(),
                payload.get("status") or "todo",
                start_at.strftime("%a"),
                title,
                start_at,
                end_at,
                payload.get("priority") or "medium",
                payload.get("lessonId"),
                payload.get("lessonTitle"),
                payload.get("learningState"),
                payload.get("subtopicId") or topic_id,
                payload.get("parentTopicId"),
                bool(payload.get("isPartialTopic", False)),
                payload.get("scope") or "subtopic",
                _parse_datetime(payload.get("earliestAllowedAt")),
            )
        row = await conn.fetchrow("SELECT st.*, s.name AS subject_name FROM study_tasks st JOIN subjects s ON s.id=st.subject_id WHERE st.id=$1", task_id)
    return _task_from_row(row)


async def update_task(pool: asyncpg.Pool, task_id: str, payload: dict[str, Any], user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
    allowed = {
        "topicId": "topic_id",
        "title": "title",
        "type": "type",
        "durationMinutes": "duration_minutes",
        "status": "status",
        "priority": "priority",
        "reason": "reason",
        "lessonId": "lesson_id",
        "lessonTitle": "lesson_title",
        "learningState": "learning_state",
        "subtopicId": "subtopic_id",
        "parentTopicId": "parent_topic_id",
        "isPartialTopic": "is_partial_topic",
        "scope": "scope",
    }
    fields = {column: payload[key] for key, column in allowed.items() if key in payload}
    if "startAt" in payload:
        fields["start_at"] = _parse_datetime(payload["startAt"])
        if fields["start_at"]:
            fields["scheduled_date"] = fields["start_at"].date()
            fields["day"] = fields["start_at"].strftime("%a")
    if "endAt" in payload:
        fields["end_at"] = _parse_datetime(payload["endAt"])
    if "earliestAllowedAt" in payload:
        fields["earliest_allowed_at"] = _parse_datetime(payload["earliestAllowedAt"])
    if fields:
        values = [task_id, user_id]
        sets = []
        for key, value in fields.items():
            values.append(value)
            sets.append(f"{key}=${len(values)}")
        async with pool.acquire() as conn:
            await conn.execute(f"UPDATE study_tasks SET {', '.join(sets)} WHERE id=$1 AND user_id=$2", *values)
        if fields.get("status") == "done":
            async with pool.acquire() as conn:
                task_row = await conn.fetchrow("SELECT topic_id, subject_id FROM study_tasks WHERE id=$1 AND user_id=$2", task_id, user_id)
            if task_row and task_row["topic_id"]:
                topic = await repository.get_topic(pool, task_row["topic_id"])
                if topic:
                    from app.services.mastery_service import simulate_objective_success
                    simulate_objective_success(topic, "system_quiz", total_questions=3, correct_questions=3)
                    await repository.update_topic(pool, topic)
                    await repository.set_plan_dirty(pool, user_id, True)
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT st.*, s.name AS subject_name FROM study_tasks st JOIN subjects s ON s.id=st.subject_id WHERE st.id=$1 AND st.user_id=$2", task_id, user_id)
    if not row:
        raise KeyError("Task not found")
    return _task_from_row(row)


async def delete_task(pool: asyncpg.Pool, task_id: str, user_id: str = DEFAULT_USER_ID) -> None:
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM study_tasks WHERE id=$1 AND user_id=$2", task_id, user_id)


async def list_busy_events(pool: asyncpg.Pool, params: dict[str, Any], user_id: str = DEFAULT_USER_ID) -> list[dict[str, Any]]:
    await ensure_dev_user(pool, user_id)
    await repository.ensure_busy_events_table(pool)
    query = "SELECT * FROM busy_events WHERE user_id=$1"
    values: list[Any] = [user_id]
    if params.get("start"):
        values.append(_require_datetime(params["start"], "start"))
        query += f" AND end_at >= ${len(values)}"
    if params.get("end"):
        values.append(_require_datetime(params["end"], "end"))
        query += f" AND start_at <= ${len(values)}"
    query += " ORDER BY start_at, created_at"
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *values)
    return [_busy_event_from_row(row) for row in rows]


async def create_busy_event(pool: asyncpg.Pool, payload: dict[str, Any], user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
    await ensure_dev_user(pool, user_id)
    await repository.ensure_busy_events_table(pool)
    title = _require_non_empty_text(payload.get("title"), "title")
    start_at = _require_datetime(payload.get("startAt") or payload.get("start_at"), "startAt")
    end_at = _require_datetime(payload.get("endAt") or payload.get("end_at"), "endAt")
    _require_time_order(start_at, end_at)
    reason = str(payload.get("reason") or "").strip()

    recurrence = payload.get("recurrence")
    recurrence_id = None
    frequency = recurrence.get("frequency") if recurrence else None
    
    is_custom = recurrence and frequency in {"custom_daily", "custom_weekly", "custom_monthly", "custom_yearly"}
    is_standard = recurrence and frequency in {"daily", "weekly", "monthly", "annually", "every_weekday"}

    if recurrence and (is_standard or is_custom):
        recurrence_id = f"rec_{uuid.uuid4().hex[:10]}"
        if recurrence.get("untilDate"):
            until_date = _parse_date(recurrence["untilDate"])
        elif recurrence.get("count"):
            until_date = (start_at + timedelta(days=366 * 2)).date() # safe far-future date
        else:
            # "Never" -> default to 1 year from start date
            until_date = (start_at + timedelta(days=366)).date()
    else:
        until_date = None

    if recurrence_id and until_date:
        current_start = start_at
        current_end = end_at
        inserted_rows = []
        limit = 100
        
        interval = int(recurrence.get("interval") or 1)
        by_day = recurrence.get("byDay") or []
        day_map = {
            "monday": "Mon", "tuesday": "Tue", "wednesday": "Wed", "thursday": "Thu", "friday": "Fri", "saturday": "Sat", "sunday": "Sun",
            "mon": "Mon", "tue": "Tue", "wed": "Wed", "thu": "Thu", "fri": "Fri", "sat": "Sat", "sun": "Sun"
        }
        by_day_codes = {day_map[d.lower()] for d in by_day if d.lower() in day_map}
        count_limit = int(recurrence.get("count")) if recurrence.get("count") else None
        
        count = 0
        created_count = 0
        
        async with pool.acquire() as conn:
            async with conn.transaction():
                while current_start.date() <= until_date and count < limit:
                    if count_limit is not None and created_count >= count_limit:
                        break

                    should_insert = True
                    if frequency == "every_weekday" and current_start.strftime("%a") in {"Sat", "Sun"}:
                        should_insert = False
                    elif frequency == "custom_weekly" and by_day_codes:
                        current_day_code = current_start.strftime("%a")
                        if current_day_code not in by_day_codes:
                            should_insert = False

                    if should_insert:
                        event_id = f"busy_{uuid.uuid4().hex[:10]}"
                        row = await conn.fetchrow(
                            """INSERT INTO busy_events (id, user_id, title, start_at, end_at, reason, recurrence_id)
                               VALUES ($1,$2,$3,$4,$5,$6,$7)
                               RETURNING *""",
                            event_id,
                            user_id,
                            title,
                            current_start,
                            current_end,
                            reason,
                            recurrence_id,
                        )
                        inserted_rows.append(row)
                        created_count += 1

                    if frequency in {"daily", "custom_daily"}:
                        current_start += timedelta(days=interval)
                        current_end += timedelta(days=interval)
                    elif frequency == "every_weekday":
                        current_start += timedelta(days=1)
                        current_end += timedelta(days=1)
                    elif frequency == "weekly":
                        current_start += timedelta(weeks=1)
                        current_end += timedelta(weeks=1)
                    elif frequency == "custom_weekly":
                        prev_start = current_start
                        current_start += timedelta(days=1)
                        current_end += timedelta(days=1)
                        if prev_start.weekday() == 6 and interval > 1:
                            current_start += timedelta(weeks=interval - 1)
                            current_end += timedelta(weeks=interval - 1)
                    elif frequency in {"monthly", "custom_monthly"}:
                        import calendar
                        y, m = current_start.year, current_start.month
                        m += interval
                        while m > 12:
                            m -= 12
                            y += 1
                        max_d = calendar.monthrange(y, m)[1]
                        target_day = min(current_start.day, max_d)
                        current_start = current_start.replace(year=y, month=m, day=target_day)
                        current_end = current_start + (end_at - start_at)
                    elif frequency in {"annually", "custom_yearly"}:
                        y = current_start.year + interval
                        try:
                            current_start = current_start.replace(year=y)
                        except ValueError:
                            current_start = current_start.replace(year=y, day=28)
                        current_end = current_start + (end_at - start_at)
                    else:
                        current_start += timedelta(days=1)
                        current_end += timedelta(days=1)

                    count += 1
        if not inserted_rows:
            raise ValueError("No instances created within the recurrence date range")
        first_row = inserted_rows[0]
    else:
        event_id = str(payload.get("id") or f"busy_{uuid.uuid4().hex[:10]}")
        async with pool.acquire() as conn:
            first_row = await conn.fetchrow(
                """INSERT INTO busy_events (id, user_id, title, start_at, end_at, reason, recurrence_id)
                   VALUES ($1,$2,$3,$4,$5,$6,$7)
                   RETURNING *""",
                event_id,
                user_id,
                title,
                start_at,
                end_at,
                reason,
                None,
            )

    await repository.set_plan_dirty(pool, user_id, True)
    return _busy_event_from_row(first_row)


async def update_busy_event(pool: asyncpg.Pool, event_id: str, payload: dict[str, Any], user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
    await ensure_dev_user(pool, user_id)
    await repository.ensure_busy_events_table(pool)
    current = await _get_busy_event_row(pool, event_id, user_id)
    if not current:
        raise KeyError("Busy event not found")

    title = _require_non_empty_text(payload["title"], "title") if "title" in payload else current["title"]
    start_at = _require_datetime(payload.get("startAt") or payload.get("start_at"), "startAt") if ("startAt" in payload or "start_at" in payload) else current["start_at"]
    end_at = _require_datetime(payload.get("endAt") or payload.get("end_at"), "endAt") if ("endAt" in payload or "end_at" in payload) else current["end_at"]
    _require_time_order(start_at, end_at)
    reason = str(payload.get("reason", current["reason"] or "") or "").strip()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """UPDATE busy_events
               SET title=$3, start_at=$4, end_at=$5, reason=$6
               WHERE id=$1 AND user_id=$2
               RETURNING *""",
            event_id,
            user_id,
            title,
            start_at,
            end_at,
            reason,
        )
    await repository.set_plan_dirty(pool, user_id, True)
    return _busy_event_from_row(row)


async def delete_busy_event(pool: asyncpg.Pool, event_id: str, user_id: str = DEFAULT_USER_ID, delete_series: bool = False) -> None:
    await repository.ensure_busy_events_table(pool)
    async with pool.acquire() as conn:
        if delete_series:
            rec_id = await conn.fetchval("SELECT recurrence_id FROM busy_events WHERE id=$1 AND user_id=$2", event_id, user_id)
            if rec_id:
                await conn.execute("DELETE FROM busy_events WHERE recurrence_id=$1 AND user_id=$2", rec_id, user_id)
                await repository.set_plan_dirty(pool, user_id, True)
                return
        result = await conn.execute("DELETE FROM busy_events WHERE id=$1 AND user_id=$2", event_id, user_id)
    if result.endswith(" 0"):
        raise KeyError("Busy event not found")
    await repository.set_plan_dirty(pool, user_id, True)


async def reschedule_missed(pool: asyncpg.Pool, payload: dict[str, Any], user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
    strategy = payload.get("strategy") or "keep_workload"
    start_day = _parse_date(payload.get("startDate")) or date.today()
    course_ids = _normalize_reschedule_course_ids(payload.get("courseIds") or payload.get("subjectIds") or payload.get("courseId"))
    rebuild_all = bool(payload.get("allCourses")) or not course_ids
    courses = await list_courses(pool, user_id)
    owned_course_ids = {course["id"] for course in courses}

    if not rebuild_all:
        missing = [course_id for course_id in course_ids if course_id not in owned_course_ids]
        if missing:
            raise KeyError("Course not found")

    missed = await list_tasks(pool, {"status": "missed"}, user_id)
    if not rebuild_all:
        missed = [task for task in missed if task.get("courseId") in course_ids]

    await repository.set_plan_dirty(pool, user_id, True)

    from app.services.unified_scheduler import build_selected_subjects_schedule, build_unified_schedule

    if rebuild_all:
        scheduler_result = await build_unified_schedule(pool, user_id, start_day)
        affected_course_ids = [course["id"] for course in courses]
        tasks = await list_tasks(pool, {}, user_id)
    else:
        scheduler_result = await build_selected_subjects_schedule(pool, user_id, course_ids, start_day)
        affected_course_ids = course_ids
        tasks = []
        for course_id in course_ids:
            tasks.extend(await list_tasks(pool, {"courseId": course_id}, user_id))

    # Calculate rescheduled notifications for missed tasks
    notifications: list[str] = []
    try:
        new_tasks = await list_tasks(pool, {"status": "ready"}, user_id)
        new_tasks += await list_tasks(pool, {"status": "todo"}, user_id)
        
        new_dates_by_topic: dict[str, list[str]] = {}
        for nt in new_tasks:
            tid = nt.get("topicId")
            if tid:
                s_date = nt.get("scheduledDate")
                if s_date:
                    date_str = s_date.split("T")[0] if "T" in s_date else s_date
                    new_dates_by_topic.setdefault(tid, []).append(date_str)
                    
        for tid in new_dates_by_topic:
            new_dates_by_topic[tid].sort()
            
        seen_notification_keys = set()
        for m in missed:
            tid = m.get("topicId")
            if tid and tid in new_dates_by_topic:
                today_str = start_day.isoformat()
                future_dates = [d for d in new_dates_by_topic[tid] if d >= today_str]
                if future_dates:
                    target_date = future_dates[0]
                    try:
                        parts = target_date.split("-")
                        formatted_date = f"{parts[2]}/{parts[1]}/{parts[0]}"
                    except Exception:
                        formatted_date = target_date
                        
                    missed_date_raw = m.get("scheduledDate") or ""
                    missed_date_str = missed_date_raw.split("T")[0] if "T" in missed_date_raw else missed_date_raw
                    try:
                        m_parts = missed_date_str.split("-")
                        formatted_missed_date = f"{m_parts[2]}/{m_parts[1]}/{m_parts[0]}"
                    except Exception:
                        formatted_missed_date = missed_date_str
                        
                    n_key = (tid, target_date)
                    if n_key not in seen_notification_keys:
                        seen_notification_keys.add(n_key)
                        notifications.append(
                            f"Nhiệm vụ '{m.get('topicTitle')}' (môn '{m.get('courseName')}') trễ hạn ngày {formatted_missed_date} đã được dời sang ngày {formatted_date}."
                        )
    except Exception as e:
        print(f"[reschedule_missed] Error generating notifications: {e}")

    return {
        "strategy": strategy,
        "scope": "all" if rebuild_all else "selected",
        "courseIds": affected_course_ids,
        "missedCount": len(missed),
        "warning": "High workload after rescheduling." if len(missed) > 5 else None,
        "scheduler": scheduler_result,
        "tasks": tasks,
        "notifications": notifications,
    }

def _normalize_reschedule_course_ids(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    raw_items = value if isinstance(value, list) else [value]
    course_ids: list[str] = []
    for item in raw_items:
        course_id = str(item or "").strip()
        if course_id and course_id not in course_ids:
            course_ids.append(course_id)
    return course_ids


async def get_dashboard(pool: asyncpg.Pool, user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
    await ensure_dev_user(pool, user_id)
    courses = await list_courses(pool, user_id)
    tasks = await list_tasks(pool, {}, user_id)
    today = date.today()
    today_tasks = [task for task in tasks if _date_from_iso(task.get("startAt")) == today and task.get("status") in {"todo", "ready", "rescheduled"}]
    missed = [task for task in tasks if task.get("status") == "missed"]
    weak_topics = []
    for course in courses:
        for topic in await list_topics(pool, course["id"], user_id):
            if topic["masteryPercent"] < 65 or topic["status"] in {"weak", "needs_review", "unknown"}:
                weak_topics.append(topic)
    weak_topics.sort(key=lambda item: item["masteryPercent"])
    
    import datetime as dt
    start_of_week = today - dt.timedelta(days=today.weekday())
    end_of_week = start_of_week + dt.timedelta(days=6)
    weekly_tasks = []
    for task in tasks:
        task_date = _date_from_iso(task.get("startAt"))
        if task_date and start_of_week <= task_date <= end_of_week:
            weekly_tasks.append(task)
    completed_weekly = [task for task in weekly_tasks if task.get("status") == "done"]
    user = await _user_payload(pool, user_id)
    subject = courses[0] if courses else None
    nearest = sorted([c for c in courses if c.get("examDate")], key=lambda c: c["examDate"])
    
    # Calculate Profile Metrics
    async with pool.acquire() as conn:
        async def build_profile_metrics(subject_id: str | None = None) -> dict[str, Any]:
            topic_rows = await conn.fetch(
                """SELECT id, mastery, fsrs_due_date, mastery_confidence
                   FROM topics
                   WHERE user_id=$1 AND ($2::text IS NULL OR subject_id=$2)""",
                user_id,
                subject_id,
            )

            masteries = [float(r["mastery"] or 0.0) for r in topic_rows]
            avg_m = (sum(masteries) / len(masteries)) if masteries else 0.0
            if len(masteries) < 2:
                consistency = 0.0
            else:
                variance = sum((m - avg_m) ** 2 for m in masteries) / len(masteries)
                std_dev = variance ** 0.5
                consistency = max(0.0, min(1.0, 1.0 - std_dev))

            mastered = [r for r in topic_rows if float(r["mastery"] or 0.0) >= 0.75]
            if not mastered:
                retention_reliability = 0.0
            else:
                not_overdue = [r for r in mastered if not r["fsrs_due_date"] or r["fsrs_due_date"] >= today]
                retention_reliability = len(not_overdue) / len(mastered)

            events = await conn.fetch(
                """SELECT predicted_p_correct, actual_correct
                   FROM mastery_events
                   WHERE user_id=$1 AND NOT excluded AND ($2::text IS NULL OR subject_id=$2)
                   ORDER BY created_at DESC LIMIT 30""",
                user_id,
                subject_id,
            )
            if not events:
                calibration_gap = 0.0
                calibration_score = 0.0
            else:
                avg_pred = sum(float(e["predicted_p_correct"]) for e in events) / len(events)
                avg_actual = sum(1.0 if e["actual_correct"] else 0.0 for e in events) / len(events)
                calibration_gap = abs(avg_pred - avg_actual)
                calibration_score = max(0.0, min(1.0, 1.0 - calibration_gap))

            count_rows = await conn.fetch(
                """SELECT topic_id, COUNT(*) as cnt
                   FROM mastery_events
                   WHERE user_id=$1 AND ($2::text IS NULL OR subject_id=$2)
                   GROUP BY topic_id""",
                user_id,
                subject_id,
            )
            evidence_counts = {r["topic_id"]: r["cnt"] for r in count_rows}

            weighted_sum = 0.0
            total_weight = 0.0
            for r in topic_rows:
                conf = float(r["mastery_confidence"] or 0.0)
                ev_cnt = evidence_counts.get(r["id"], 0)
                w = 1.0 + float(ev_cnt)
                weighted_sum += conf * w
                total_weight += w
            engagement_confidence = (weighted_sum / total_weight) if total_weight > 0.0 else 0.0

            all_events = await conn.fetch(
                """SELECT predicted_p_correct, actual_correct
                   FROM mastery_events
                   WHERE user_id=$1 AND NOT excluded AND ($2::text IS NULL OR subject_id=$2)""",
                user_id,
                subject_id,
            )
            calibration_curve = []
            bins = [(0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.0)]
            for low, high in bins:
                bin_events = [e for e in all_events if low <= float(e["predicted_p_correct"]) < high]
                if bin_events:
                    bin_pred = sum(float(e["predicted_p_correct"]) for e in bin_events) / len(bin_events)
                    bin_actual = sum(1.0 if e["actual_correct"] else 0.0 for e in bin_events) / len(bin_events)
                    calibration_curve.append({
                        "bin": f"{int(low*100)}-{int(high*100)}%",
                        "predicted": round(bin_pred, 3),
                        "actual": round(bin_actual, 3),
                        "count": len(bin_events)
                    })
                else:
                    calibration_curve.append({
                        "bin": f"{int(low*100)}-{int(high*100)}%",
                        "predicted": round((low + high)/2, 3),
                        "actual": None,
                        "count": 0
                    })

            trend_rows = await conn.fetch(
                """SELECT DATE(created_at) as day, AVG(p_l_after) as avg_mastery
                   FROM mastery_events
                   WHERE user_id=$1 AND ($2::text IS NULL OR subject_id=$2)
                   GROUP BY DATE(created_at)
                   ORDER BY day ASC""",
                user_id,
                subject_id,
            )
            mastery_trends = []
            import datetime as dt
            day_map = {r["day"]: float(r["avg_mastery"]) for r in trend_rows}
            for i in range(13, -1, -1):
                d = today - dt.timedelta(days=i)
                val = day_map.get(d)
                if val is None:
                    val = avg_m if masteries else 0.0
                mastery_trends.append({
                    "date": d.isoformat(),
                    "mastery": round(val, 3)
                })

            return {
                "knowledgeConsistency": round(consistency * 100),
                "retentionReliability": round(retention_reliability * 100),
                "personalCalibrationScore": round(calibration_score * 100),
                "calibrationGap": round(calibration_gap * 100),
                "engagementConfidence": round(engagement_confidence * 100),
                "calibrationCurve": calibration_curve,
                "masteryTrends": mastery_trends,
                "topicCount": len(topic_rows),
                "eventCount": len(all_events),
            }

        profile_metrics = await build_profile_metrics()
        profile_metrics_by_course = {}
        for course in courses:
            profile_metrics_by_course[course["id"]] = await build_profile_metrics(course["id"])

    return {
        "status": "success",
        "user": user,
        "todayTasks": sorted(today_tasks, key=lambda item: item.get("startAt") or ""),
        "missedTasks": missed,
        "courses": courses,
        "weakTopics": weak_topics[:6],
        "weeklyStats": {
            "progressPercent": round((len(completed_weekly) / len(weekly_tasks)) * 100) if weekly_tasks else 0,
            "completedTasks": len(completed_weekly),
            "totalTasks": len(weekly_tasks),
            "minutesStudied": sum(int(task.get("durationMinutes") or 0) for task in completed_weekly),
            "streakDays": 3 if completed_weekly else 0,
        },
        "nearestDeadline": {"courseId": nearest[0]["id"], "courseName": nearest[0]["name"], "label": f"Exam on {nearest[0]['examDate']}"} if nearest else None,
        "nextSchedule": sorted(today_tasks, key=lambda item: item.get("priority") == "high", reverse=True)[0] if today_tasks else None,
        "subject": subject,
        "readiness": subject.get("readinessPercent", 0) if subject else 0,
        "streak": 3 if completed_weekly else 0,
        "xp": user.get("xp", 0),
        "coverageWarning": None,
        "mascotMessage": "Keep going!" if courses else "Create your first course to start studying.",
        "profileMetrics": {
            **profile_metrics,
            "byCourse": profile_metrics_by_course,
        },
    }


async def list_chat_threads(pool: asyncpg.Pool, course_id: str, user_id: str = DEFAULT_USER_ID) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM chat_threads WHERE subject_id=$1 AND user_id=$2 ORDER BY updated_at DESC", course_id, user_id)
    return [_thread_from_row(row) for row in rows]


async def create_chat_thread(pool: asyncpg.Pool, payload: dict[str, Any], user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
    course_id = payload.get("courseId")
    if not course_id:
        raise ValueError("courseId is required")
    thread_id = f"thread_{uuid.uuid4().hex[:10]}"
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO chat_threads (id, subject_id, user_id, title, origin) VALUES ($1,$2,$3,$4,$5)",
            thread_id,
            course_id,
            user_id,
            payload.get("title") or "New conversation",
            payload.get("origin") or "normal",
        )
        row = await conn.fetchrow("SELECT * FROM chat_threads WHERE id=$1", thread_id)
    return _thread_from_row(row)


async def list_chat_messages(pool: asyncpg.Pool, thread_id: str, user_id: str = DEFAULT_USER_ID) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM chat_messages WHERE thread_id=$1 AND user_id=$2 ORDER BY created_at", thread_id, user_id)
    return [_message_from_row(row) for row in rows]


async def delete_chat_thread(pool: asyncpg.Pool, thread_id: str, user_id: str = DEFAULT_USER_ID) -> None:
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM chat_threads WHERE id=$1 AND user_id=$2", thread_id, user_id)


async def _route_query(message: str) -> dict[str, Any]:
    lower_msg = message.lower().strip()
    if lower_msg in ["hello", "hi", "xin chào", "chào bạn", "hello tutor", "hi tutor", "chào"]:
        return {"route": "GENERAL_CHAT", "tool": None}
        
    unsupported_keywords = [
        "chế tạo bom", "hack", "ddos", "tự tử", "vũ khí", "bom mìn",
        "suicide", "make bomb", "how to kill", "weather", "thời tiết",
        "nấu ăn", "recipe", "cake", "bánh", "president", "tổng thống"
    ]
    if any(kw in lower_msg for kw in unsupported_keywords):
        return {"route": "UNSUPPORTED", "tool": None}
        
    import asyncio
    import json
    from app.core.document.llm_section_split import complete_text
    
    system_content = ROUTER_SYSTEM_PROMPT
    try:
        response = await asyncio.to_thread(
            complete_text,
            [
                {"role": "system", "content": system_content},
                {"role": "user", "content": message}
            ],
            0.1,
            150
        )
        text = response.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        parsed = json.loads(text)
        if parsed.get("route") not in ["TOOL_CALL", "GENERAL_CHAT", "RAG_SEARCH", "UNSUPPORTED"]:
            parsed["route"] = "RAG_SEARCH"
        return parsed
    except Exception:
        return {"route": "RAG_SEARCH", "tool": None}


async def send_rag_chat(pool: asyncpg.Pool, payload: dict[str, Any], user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
    course_id = payload.get("courseId")
    message = str(payload.get("message") or "").strip()
    if not course_id or not message:
        raise ValueError("courseId and message are required")
        
    from app.core.agent.guardrails import guardrail_check_input, guardrail_check_output
    
    cleaned_message, is_safe, input_issues = guardrail_check_input(message)
    if not is_safe:
        thread_id = payload.get("threadId")
        thread = await _get_thread(pool, thread_id, user_id) if thread_id else None
        if not thread:
            thread = await create_chat_thread(
                pool,
                {
                    "courseId": course_id,
                    "title": message[:48],
                    "origin": "normal"
                },
                user_id
            )
        thread_id = thread["id"]
        user_message = await _insert_message(pool, thread_id, user_id, "user", message, [], [])
        answer_text = "Xin lỗi, tin nhắn của bạn chứa nội dung không an toàn hoặc vi phạm chính sách bảo mật."
        assistant_message = await _insert_message(pool, thread_id, user_id, "assistant", answer_text, [], [])
        async with pool.acquire() as conn:
            await conn.execute("UPDATE chat_threads SET updated_at=now() WHERE id=$1", thread_id)
        return {
            "id": thread_id,
            "title": thread["title"],
            "messages": [user_message, assistant_message]
        }
        
    message = cleaned_message
        
    request_context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    is_quiz_in_progress = request_context.get("type") == "quiz_in_progress"
    is_quiz_explain = (
        request_context.get("type") == "quiz_mistake" or
        message.startswith("Giải thích sâu hơn câu quiz") or
        ("Đáp án đúng:" in message and "Nguồn:" in message)
    )
    
    thread_id = payload.get("threadId")
    thread = await _get_thread(pool, thread_id, user_id) if thread_id else None
    if not thread:
        thread = await create_chat_thread(
            pool,
            {
                "courseId": course_id,
                "title": message[:48],
                "origin": "quiz_result" if is_quiz_explain else "normal"
            },
            user_id
        )
    thread_id = thread["id"]
    
    user_message = await _insert_message(pool, thread_id, user_id, "user", message, [], [])
    
    history_messages = await list_chat_messages(pool, thread_id, user_id)
    history_history = []
    if len(history_messages) > 1:
        for m in history_messages[:-1][-15:]:
            history_history.append({"role": m["role"], "content": m["content"]})
            
    ranked = []
    refs = []
    actions = []
    _debug = {}
    answer_text = ""
    
    if is_quiz_in_progress:
        answer_text = (
            "Vui lòng hoàn thành quiz hiện tại trước khi hỏi AI. "
            "Trong lúc bạn đang làm bài, StudyFlow sẽ không gợi ý, giải thích hoặc cung cấp đáp án để kết quả phản ánh đúng năng lực của bạn."
        )
        _debug = {
            "mode": "quiz_in_progress_guard",
            "quiz_id": request_context.get("quizId"),
            "answered_count": request_context.get("answeredCount"),
            "total_questions": request_context.get("totalQuestions"),
        }

    elif is_quiz_explain:
        chunk_text = ""
        source_ref = request_context.get("sourceRef") or {}
        chunk_ids = source_ref.get("chunkIds") or []
        if not chunk_ids and source_ref.get("chunkId"):
            chunk_ids = [source_ref.get("chunkId")]
        if not chunk_ids and source_ref.get("id"):
            val = source_ref.get("id")
            if isinstance(val, str) and val.startswith("chunk_"):
                chunk_ids = [val]
                
        if chunk_ids:
            async with pool.acquire() as conn:
                rows = await conn.fetch("SELECT text FROM document_chunks WHERE id = ANY($1)", chunk_ids)
                if rows:
                    chunk_text = "\n\n".join(row["text"] for row in rows)
        
        if not chunk_text:
            chunk_text = source_ref.get("quote") or source_ref.get("passage") or ""
            
        if chunk_text:
            refs = [source_ref]
            
        from app.core.document.llm_section_split import get_openai_client
        client = get_openai_client()
        
        system_content = (
            "You are StudyFlow's course tutor. Answer in Vietnamese. "
            "The user needs you to explain a quiz question. "
            "Below is the relevant chunk text retrieved from the document:\n"
            f"--- START DOCUMENT CONTEXT ---\n{chunk_text}\n--- END DOCUMENT CONTEXT ---\n\n"
            "The user query contains the question text, their chosen answer, the correct answer, "
            "and the brief explanation of the correct answer along with source file/chunk references. "
            "Using this information and the document context above, write a detailed, clear, and pedagogical explanation in Vietnamese "
            "on why the correct answer is correct and why the user's selected answer is incorrect/incomplete. "
            "Be encouraging and academic. Keep the explanation structured, clear, and helpful."
        )
        
        messages = [
            {"role": "system", "content": system_content},
            *history_history,
            {"role": "user", "content": message}
        ]
        
        from app.config import settings
        kwargs = {
            "model": settings.LLM_MODEL,
            "messages": messages,
            "temperature": 0.5,
            "max_tokens": 1000
        }
        if settings.LLM_TOP_P is not None:
            kwargs["top_p"] = settings.LLM_TOP_P
            
        completion = client.chat.completions.create(**kwargs)
        answer_text = completion.choices[0].message.content or ""
        _debug = {"mode": "quiz_explain", "chunk_ids": chunk_ids}
        
    else:
        selected_source_ids = payload.get("selectedDocumentIds") or payload.get("selectedSourceIds") or []
        selected_topic_ids = payload.get("selectedTopicIds") or payload.get("topicIds") or []
        try:
            from app.core.agent.react_agent import run_studyflow_agent

            answer_text = await run_studyflow_agent(
                pool,
                course_id,
                user_id,
                message,
                history_history,
                selected_source_ids=selected_source_ids,
                selected_topic_ids=selected_topic_ids
            )
            _debug = {"mode": "langchain_react_agent"}
        except ModuleNotFoundError as error:
            answer_text = await _fallback_plain_chat_completion(message, history_history)
            _debug = {"mode": "plain_chat_fallback", "reason": str(error)}
        refs = []
                
    actions = [] if is_quiz_in_progress else [
        {"label": "Create 5 flashcards", "type": "generate_flashcards", "payload": {"courseId": course_id, "count": 5}},
        {"label": "Make 3 quiz questions", "type": "generate_quiz", "payload": {"courseId": course_id, "count": 3}},
        {"label": "Explain simpler", "type": "explain_simpler", "payload": {"courseId": course_id}},
    ]
    if _debug and "hops_taken" in _debug:
        actions.append({
            "type": "reasoning_hops",
            "hops": _debug["hops_taken"]
        })
        
    # Check output guardrails
    cleaned_answer, _, _ = guardrail_check_output(answer_text)
    answer_text = cleaned_answer

    assistant_message = await _insert_message(pool, thread_id, user_id, "assistant", answer_text, refs, actions)
    async with pool.acquire() as conn:
        await conn.execute("UPDATE chat_threads SET updated_at=now() WHERE id=$1", thread_id)
        
    return {
        "threadId": thread_id,
        "answer": answer_text,
        "sourceRefs": refs,
        "actions": actions,
        "messages": [user_message, assistant_message],
        "debug": _debug
    }


async def list_chunks(pool: asyncpg.Pool, course_id: str, user_id: str = DEFAULT_USER_ID) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT *, (embedding::real[]) as embedding FROM document_chunks WHERE subject_id=$1 AND user_id=$2 ORDER BY source_id, chunk_index", course_id, user_id)
    return [_chunk_from_row(row) for row in rows]


async def generate_quiz(pool: asyncpg.Pool, payload: dict[str, Any], user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
    course_id = payload.get("courseId")
    if not course_id:
        raise ValueError("courseId is required")
    await _assert_topic_practice_allowed(pool, course_id, user_id, payload)
    course = await get_course(pool, course_id, user_id)
    count = max(1, min(50, int(payload.get("count") or 20)))
    has_selection = isinstance(payload.get("selectedSourceIds"), list)
    selected = payload.get("selectedSourceIds") if has_selection else []
    requested_topic_ids = {str(value) for value in payload.get("topicIds") or []} if isinstance(payload.get("topicIds"), list) else set()
    if has_selection and not selected:
        chunks = []
    else:
        chunks_for_practice = await _filter_chunks_for_syllabus(pool, course_id, user_id, await list_chunks(pool, course_id, user_id), payload)
        if requested_topic_ids:
            chunks_for_practice = [chunk for chunk in chunks_for_practice if any(topic_id in requested_topic_ids for topic_id in chunk.get("topicIds") or [])]
        chunks, _refs, _debug = retrieve_chunks(chunks_for_practice, payload.get("query") or course["name"], selected, limit=max(8, count * 2))
    req_topic_id = payload.get("topicId")
    if not req_topic_id and requested_topic_ids:
        req_topic_id = next(iter(requested_topic_ids))
    questions = await _build_quiz_questions(course, chunks, count, req_topic_id, payload)
    if requested_topic_ids:
        fallback_topic_id = next(iter(requested_topic_ids))
        for question in questions:
            if question.get("topicId") not in requested_topic_ids:
                question["topicId"] = fallback_topic_id
    quiz_id = f"quiz_{uuid.uuid4().hex[:10]}"
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO practice_quizzes (id, subject_id, user_id, topic_id, title, difficulty, instructions, selected_source_ids, questions)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)""",
            quiz_id,
            course_id,
            user_id,
            req_topic_id,
            payload.get("title") or f"Practice quiz: {course['name']}",
            payload.get("difficulty") or "medium",
            payload.get("instructions") or payload.get("query") or "",
            selected,
            questions,
        )
        row = await conn.fetchrow("SELECT * FROM practice_quizzes WHERE id=$1", quiz_id)
    return _quiz_from_row(row)


async def list_quizzes(pool: asyncpg.Pool, course_id: str, user_id: str = DEFAULT_USER_ID) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM practice_quizzes WHERE subject_id=$1 AND user_id=$2 ORDER BY created_at DESC", course_id, user_id)
    return [_quiz_from_row(row) for row in rows]


async def get_quiz(pool: asyncpg.Pool, quiz_id: str, user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM practice_quizzes WHERE id=$1 AND user_id=$2", quiz_id, user_id)
    if not row:
        raise KeyError("Quiz not found")
    return _quiz_from_row(row)


async def create_quiz_result(pool: asyncpg.Pool, payload: dict[str, Any], user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
    quiz = await get_quiz(pool, payload.get("quizId"), user_id)
    answers = _answers_by_question_id(payload.get("answersByQuestionId") or payload.get("answers") or {})
    score = 0
    mistakes = []
    topic_updates: dict[str, list[BatchQuestionOutcome]] = {}
    for question in quiz["questions"]:
        selected = answers.get(question["id"])
        correct = question.get("correctAnswer") or question.get("answer")
        is_correct = selected == correct
        if is_correct:
            score += 1
        else:
            mistakes.append({
                "questionId": question["id"],
                "topicName": question.get("topicName") or "General",
                "question": question.get("question") or question.get("prompt"),
                "selectedAnswer": selected or "No answer",
                "correctAnswer": correct,
                "explanation": question.get("explanation") or "Based on the selected source material.",
                "sourceRef": question.get("sourceRef"),
            })
        if question.get("topicId") and selected is not None:
            topic_updates.setdefault(question["topicId"], []).append(BatchQuestionOutcome(correct=is_correct, question_format="mcq_4"))
    total = len(quiz["questions"])
    accuracy = round((score / total) * 100) if total else 0
    result_id = f"result_{uuid.uuid4().hex[:10]}"
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO practice_quiz_results (id, quiz_id, subject_id, user_id, score, total, accuracy_percent,
                                                   average_seconds_per_question, mistakes)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)""",
            result_id,
            quiz["id"],
            quiz["courseId"],
            user_id,
            score,
            total,
            accuracy,
            int(payload.get("averageSecondsPerQuestion") or 45),
            mistakes,
        )
        row = await conn.fetchrow("SELECT * FROM practice_quiz_results WHERE id=$1", result_id)
    if topic_updates:
        await _apply_topic_practice_updates(pool, user_id, quiz["courseId"], topic_updates, "workspace_quiz", result_id)
    task_id = payload.get("taskId")
    if task_id:
        await repository.update_task_status(pool, task_id, "done")
    return _quiz_result_from_row(row)


async def get_quiz_result(pool: asyncpg.Pool, result_id: str, user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM practice_quiz_results WHERE id=$1 AND user_id=$2", result_id, user_id)
    if not row:
        raise KeyError("Quiz result not found")
    return _quiz_result_from_row(row)


async def generate_flashcards(pool: asyncpg.Pool, payload: dict[str, Any], user_id: str = DEFAULT_USER_ID) -> list[dict[str, Any]]:
    course_id = payload.get("courseId")
    if not course_id:
        raise ValueError("courseId is required")
    await _assert_topic_practice_allowed(pool, course_id, user_id, payload)
    course = await get_course(pool, course_id, user_id)
    count = max(1, min(50, int(payload.get("count") or 5)))
    has_selection = isinstance(payload.get("selectedSourceIds"), list)
    selected = payload.get("selectedSourceIds") if has_selection else []
    requested_topic_ids = {str(value) for value in payload.get("topicIds") or []} if isinstance(payload.get("topicIds"), list) else set()
    if has_selection and not selected:
        chunks = []
    else:
        chunks_for_practice = await _filter_chunks_for_syllabus(pool, course_id, user_id, await list_chunks(pool, course_id, user_id), payload)
        if requested_topic_ids:
            chunks_for_practice = [chunk for chunk in chunks_for_practice if any(topic_id in requested_topic_ids for topic_id in chunk.get("topicIds") or [])]
        chunks, _refs, _debug = retrieve_chunks(chunks_for_practice, payload.get("query") or course["name"], selected, limit=max(6, count))
    req_topic_id = payload.get("topicId")
    if not req_topic_id and requested_topic_ids:
        req_topic_id = next(iter(requested_topic_ids))
    cards_payload = await _build_flashcards(course, chunks, count, req_topic_id)
    cards = []
    # When multiple topicIds were requested, only fall back to req_topic_id
    # (first topic in the set) if the generator did NOT tag the card AND
    # exactly one topic was requested — avoids mis-attributing cards to an
    # arbitrary topic when several topics were in scope.
    multi_topic_requested = len(requested_topic_ids) > 1
    async with pool.acquire() as conn:
        for card in cards_payload:
            card_id = f"flashcard_{uuid.uuid4().hex[:10]}"
            card_topic_id = card.get("topicId")
            if not card_topic_id and not multi_topic_requested:
                card_topic_id = req_topic_id
            await conn.execute(
                """INSERT INTO flashcards (id, subject_id, user_id, topic_id, front, back, explanation, source_ref, due_at)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,now())""",
                card_id,
                course_id,
                user_id,
                card_topic_id,
                card["front"],
                card["back"],
                card.get("explanation") or "",
                card.get("sourceRef"),
            )
            row = await conn.fetchrow("SELECT * FROM flashcards WHERE id=$1", card_id)
            cards.append(_flashcard_from_row(row))
    return cards


async def list_flashcards(pool: asyncpg.Pool, course_id: str, user_id: str = DEFAULT_USER_ID) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM flashcards WHERE subject_id=$1 AND user_id=$2 ORDER BY due_at NULLS FIRST, created_at DESC", course_id, user_id)
    return [_flashcard_from_row(row) for row in rows]


async def create_flashcard_session(pool: asyncpg.Pool, payload: dict[str, Any], user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
    course_id = payload.get("courseId")
    count = int(payload.get("count") or 10)
    await _assert_topic_practice_allowed(pool, course_id, user_id, payload)
    cards = await list_flashcards(pool, course_id, user_id)
    has_active_syllabus = await _has_active_syllabus(pool, course_id, user_id)
    allowed_ids = set(await _allowed_topic_ids(pool, course_id, user_id))
    if has_active_syllabus:
        cards = [card for card in cards if not card.get("topicId") or card.get("topicId") in allowed_ids]
        if not allowed_ids and not cards:
            raise ValueError("No taught or current syllabus topics are available for flashcard practice")
    if not cards:
        cards = await generate_flashcards(pool, {"courseId": course_id, "count": min(count, 5)}, user_id)
    selected = cards[:count]
    session_id = f"flash_session_{uuid.uuid4().hex[:10]}"
    ids = [card["id"] for card in selected]
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO flashcard_sessions (id, subject_id, user_id, flashcard_ids, ratings, status) VALUES ($1,$2,$3,$4,$5,'in_progress')",
            session_id,
            course_id,
            user_id,
            ids,
            {},
        )
        row = await conn.fetchrow("SELECT * FROM flashcard_sessions WHERE id=$1", session_id)
    return {**_flashcard_session_from_row(row), "cards": selected}


async def review_flashcard(pool: asyncpg.Pool, flashcard_id: str, rating: str, user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
    days = {"again": 1, "hard": 2, "good": 4, "easy": 7}.get(str(rating).lower(), 1)
    due = datetime.now(timezone.utc) + timedelta(days=days)
    async with pool.acquire() as conn:
        row = await conn.fetchrow("UPDATE flashcards SET last_rating=$3, due_at=$4 WHERE id=$1 AND user_id=$2 RETURNING *", flashcard_id, user_id, rating, due)
    if not row:
        raise KeyError("Flashcard not found")
    topic_id = row["topic_id"]
    if topic_id:
        normalized = _normalize_fsrs_rating(rating) or "Again"
        await _apply_topic_practice_updates(
            pool,
            user_id,
            row["subject_id"],
            {topic_id: {"rating": normalized}},
            "flashcard",
            flashcard_id,
        )
    return _flashcard_from_row(row)


async def _apply_topic_practice_updates(
    pool: asyncpg.Pool,
    user_id: str,
    course_id: str,
    updates: dict[str, Any],
    evidence_source: str = "workspace_quiz",
    source_id: str | None = None,
) -> None:
    profile = await repository.get_profile(pool, user_id)
    scheduler = get_scheduler(profile.fsrs_custom_weights if profile else None)
    today = date.today()
    touched = False

    for topic_id, payload in updates.items():
        topic = await repository.get_topic(pool, topic_id)
        if not topic or topic.subject_id != course_id or topic.user_id != user_id:
            continue

        previous_review = topic.fsrs_last_review
        previous_state = int(topic.fsrs_state or 0)
        normalized_rating = _normalize_fsrs_rating((payload or {}).get("rating")) if isinstance(payload, dict) else None
        outcomes = (payload or {}).get("outcomes") if isinstance(payload, dict) else payload
        if evidence_source != "flashcard" and outcomes:
            normalized_rating = normalized_rating or _batch_rating(outcomes)
            batch_source_id = source_id or f"practice-{uuid.uuid4().hex[:10]}:{topic_id}"
            await apply_objective_batch(
                pool,
                topic,
                user_id=user_id,
                subject_id=course_id,
                source_type=evidence_source,
                source_id=batch_source_id,
                outcomes=outcomes,
                is_diagnostic=False,
            )
        else:
            normalized_rating = normalized_rating or "Again"

        FSRSScheduler.update(topic, normalized_rating, today, scheduler)
        topic.fsrs_due_date = _due_date_from_card(topic)

        elapsed_days = max(0, (today - previous_review).days) if previous_review else 0
        await repository.append_review_log(pool, FsrsReviewLog(
            id=f"log-{uuid.uuid4()}",
            user_id=user_id,
            subject_id=course_id,
            item_id=topic.id,
            rating=RATING_TO_INT[normalized_rating],
            review_date=datetime.now(timezone.utc),
            elapsed_days=elapsed_days,
            review_state=previous_state,
        ))
        await repository.update_topic(pool, topic)
        touched = True

    if touched:
        await repository.set_plan_dirty(pool, user_id, True)


def _normalize_fsrs_rating(value: str | None) -> str | None:
    if not value:
        return None
    lookup = {key.lower(): key for key in RATING_TO_INT}
    return lookup.get(str(value).lower())


def _batch_rating(outcomes: list[BatchQuestionOutcome]) -> str:
    total = len(outcomes)
    correct = sum(1 for outcome in outcomes if outcome.correct)
    if total <= 0:
        return "Again"
    accuracy = correct / total
    if accuracy >= 0.95:
        return "Easy"
    if accuracy >= 0.60:
        return "Good"
    if accuracy > 0:
        return "Hard"
    return "Again"


def _due_date_from_card(topic) -> date | None:
    due = topic.fsrs_card.get("due") or topic.fsrs_card.get("due_date")
    if not due:
        return topic.fsrs_due_date
    try:
        return datetime.fromisoformat(str(due).replace("Z", "+00:00")).date()
    except Exception:
        return topic.fsrs_due_date


async def generic_chat(body: dict[str, Any]) -> dict[str, Any]:
    messages = body.get("messages") or []
    content = messages[-1].get("content", "") if messages else ""
    answer = await _general_llm_answer(content)
    return {"status": "success", "provider": "llm", "message": {"role": "assistant", "content": answer}, "sources": []}


async def _replace_chunks_and_topics(
    pool: asyncpg.Pool,
    source: dict[str, Any],
    chunks: list[dict[str, Any]],
    topics: list[dict[str, Any]],
    user_id: str,
    replace_source_topics: bool = False,
) -> None:
    async with pool.acquire() as conn:
        embedding_uses_array = await _embedding_column_uses_array(conn)
        async with conn.transaction():
            await conn.execute("DELETE FROM document_chunks WHERE source_id=$1 AND user_id=$2", source["id"], user_id)
            if replace_source_topics:
                prefix = f"topic-{source['courseId']}-{source['id']}-"
                await conn.execute(
                    "DELETE FROM topics WHERE subject_id=$1 AND user_id=$2 AND left(id, length($3)) = $3",
                    source["courseId"],
                    user_id,
                    prefix,
                )
            for chunk in chunks:
                await conn.execute(
                    """INSERT INTO document_chunks (id, subject_id, source_id, user_id, filename, chunk_index, text, normalized_text,
                                                    quote, page, page_start, page_end, section_path, section_title, topic_ids,
                                                    content_hash, token_count, embedding_status, metadata, embedding)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20)
                       ON CONFLICT (id) DO UPDATE SET text=EXCLUDED.text, normalized_text=EXCLUDED.normalized_text,
                         quote=EXCLUDED.quote, page=EXCLUDED.page, page_start=EXCLUDED.page_start,
                         page_end=EXCLUDED.page_end, section_path=EXCLUDED.section_path,
                         section_title=EXCLUDED.section_title, topic_ids=EXCLUDED.topic_ids, embedding=EXCLUDED.embedding""",
                    chunk["id"], source["courseId"], source["id"], user_id, chunk["filename"], chunk["chunkIndex"], chunk["text"],
                    chunk["normalizedText"], chunk["quote"], chunk.get("page"), chunk.get("pageStart"), chunk.get("pageEnd"),
                    chunk.get("sectionPath") or "", chunk.get("sectionTitle") or "", chunk.get("topicIds") or [], chunk.get("contentHash") or "",
                    int(chunk.get("tokenCount") or 0), chunk.get("embeddingStatus") or "disabled", {}, _embedding_db_value(chunk.get("embedding"), embedding_uses_array),
            )
    await _save_topics(pool, topics)

async def _replace_course_index(pool: asyncpg.Pool, course_id: str, user_id: str, prepared: list[dict[str, Any]]) -> None:
    async with pool.acquire() as conn:
        embedding_uses_array = await _embedding_column_uses_array(conn)
        async with conn.transaction():
            await conn.execute("DELETE FROM document_chunks WHERE subject_id=$1 AND user_id=$2", course_id, user_id)
            for item in prepared:
                source = item["source"]
                for chunk in item["chunks"]:
                    await conn.execute(
                        """INSERT INTO document_chunks (id, subject_id, source_id, user_id, filename, chunk_index, text, normalized_text,
                                                        quote, page, page_start, page_end, section_path, section_title, topic_ids,
                                                        content_hash, token_count, embedding_status, metadata, embedding)
                           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20)""",
                        chunk["id"], course_id, source["id"], user_id, chunk["filename"], chunk["chunkIndex"], chunk["text"],
                        chunk["normalizedText"], chunk["quote"], chunk.get("page"), chunk.get("pageStart"), chunk.get("pageEnd"),
                        chunk.get("sectionPath") or "", chunk.get("sectionTitle") or "", chunk.get("topicIds") or [], chunk.get("contentHash") or "",
                        int(chunk.get("tokenCount") or 0), chunk.get("embeddingStatus") or "disabled", {}, _embedding_db_value(chunk.get("embedding"), embedding_uses_array),
                    )
                await conn.execute(
                    "UPDATE course_sources SET status='ready', parsed_at=now(), topic_count=$3, error_message=NULL WHERE id=$1 AND user_id=$2",
                    source["id"],
                    user_id,
                    len(item["topics"]),
                )


async def _embedding_column_uses_array(conn: asyncpg.Connection) -> bool:
    udt_name = await conn.fetchval(
        """
        SELECT udt_name
        FROM information_schema.columns
        WHERE table_name='document_chunks' AND column_name='embedding'
        """
    )
    return udt_name in {"_float4", "_float8"}


def _embedding_db_value(embedding: Any, uses_array: bool) -> Any:
    if embedding is None:
        return None
    return embedding if uses_array else str(embedding)


async def _save_topics(pool: asyncpg.Pool, topics: list[dict[str, Any]]) -> None:
    if not topics:
        return
    async with pool.acquire() as conn:
        for t in topics:
            await conn.execute(
                """INSERT INTO topics (id, subject_id, user_id, title, description, section_number, content_chunk, order_idx,
                                        cost_mins, mastery, p_l0, p_t, p_g, p_s, awaiting_diagnostic, fsrs_card,
                                        fsrs_stability, fsrs_difficulty, fsrs_last_review, fsrs_due_date, merged_from, is_learned,
                                        parent_topic_id, parent_topic_title, is_subtopic, lesson_id, learning_state, practice_allowed)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24,$25,$26,$27,$28)
                   ON CONFLICT (id) DO UPDATE SET description=EXCLUDED.description, content_chunk=EXCLUDED.content_chunk,
                     parent_topic_id=EXCLUDED.parent_topic_id, parent_topic_title=EXCLUDED.parent_topic_title,
                     is_subtopic=EXCLUDED.is_subtopic,
                     lesson_id=COALESCE(EXCLUDED.lesson_id, topics.lesson_id), learning_state=EXCLUDED.learning_state,
                     practice_allowed=EXCLUDED.practice_allowed""",
                t["id"], t["subject_id"], t["user_id"], t["title"], t.get("description", ""), t.get("section_number", 0),
                t.get("content_chunk", ""), t.get("order_idx", 0), t.get("cost_mins", 30), t.get("mastery", 0.05),
                t.get("p_l0", 0.05), t.get("p_t", 0.2), t.get("p_g", 0.2), t.get("p_s", 0.1), t.get("awaiting_diagnostic", True),
                t.get("fsrs_card") or {}, t.get("fsrs_stability", 0.0), t.get("fsrs_difficulty", 5.0), t.get("fsrs_last_review"),
                t.get("fsrs_due_date"), t.get("merged_from") or [], t.get("is_learned", False),
                t.get("parent_topic_id"), t.get("parent_topic_title"), t.get("is_subtopic", True),
                t.get("lesson_id"), t.get("learning_state", "taught"), t.get("practice_allowed", True),
            )


async def _course_row(pool: asyncpg.Pool, course_id: str, user_id: str) -> asyncpg.Record | None:
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """SELECT s.*,
                      (SELECT COUNT(*) FROM course_sources cs WHERE cs.subject_id=s.id) AS source_count,
                      (SELECT COUNT(*) FROM topics t WHERE t.subject_id=s.id) AS topic_count,
                      (SELECT COUNT(*) FROM study_tasks st WHERE st.subject_id=s.id) AS task_count,
                      COALESCE((SELECT AVG(t.mastery) FROM topics t WHERE t.subject_id=s.id), 0) AS mastery_avg,
                      COALESCE((SELECT AVG(t.mastery_confidence) FROM topics t WHERE t.subject_id=s.id), 0) AS confidence_avg,
                      (SELECT sy.status FROM course_syllabi sy WHERE sy.subject_id=s.id ORDER BY sy.created_at DESC LIMIT 1) AS syllabus_status,
                      (SELECT sy.current_week FROM course_syllabi sy WHERE sy.subject_id=s.id ORDER BY sy.created_at DESC LIMIT 1) AS current_week,
                      (SELECT sy.current_lesson_id FROM course_syllabi sy WHERE sy.subject_id=s.id ORDER BY sy.created_at DESC LIMIT 1) AS current_lesson_id,
                      (SELECT sl.title FROM course_syllabi sy JOIN syllabus_lessons sl ON sl.id=sy.current_lesson_id WHERE sy.subject_id=s.id ORDER BY sy.created_at DESC LIMIT 1) AS current_lesson_title
               FROM subjects s
               WHERE s.id=$1 AND s.user_id=$2""",
            course_id,
            user_id,
        )


async def _require_course(pool: asyncpg.Pool, course_id: str, user_id: str) -> None:
    if not await _course_row(pool, course_id, user_id):
        raise KeyError("Course not found")


async def _user_payload(pool: asyncpg.Pool, user_id: str) -> dict[str, Any]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE id=$1", user_id)
    return {"id": user_id, "name": "StudyFlow Test User" if user_id == DEFAULT_USER_ID else (row["email"].split("@")[0] if row else user_id), "email": row["email"] if row else f"{user_id}@local.studyflow", "xp": row["xp"] if row else 0, "avatarUrl": ""}


def _syllabus_from_row(row: asyncpg.Record | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "id": row["id"],
        "courseId": row["subject_id"],
        "sourceType": row["source_type"],
        "status": row["status"],
        "rawText": row["raw_text"],
        "parsedJson": _json_value(row["parsed_json"], {}),
        "currentLessonId": row["current_lesson_id"],
        "currentWeek": row["current_week"],
        "joinPosition": row["join_position"],
        "createdAt": _iso(row["created_at"]),
        "updatedAt": _iso(row["updated_at"]),
    }


def _lesson_from_row(row: asyncpg.Record) -> dict[str, Any]:
    return {
        "id": row["id"],
        "courseId": row["subject_id"],
        "syllabusId": row["syllabus_id"],
        "weekNumber": row["week_number"],
        "lessonNumber": row["lesson_number"],
        "title": row["title"],
        "description": row["description"],
        "assignedReadings": list(row["assigned_readings"] or []),
        "startsOn": _iso(row["starts_on"]),
        "endsOn": _iso(row["ends_on"]),
        "status": row["status"],
        "orderIdx": row["order_idx"],
    }

def _apply_class_calendar_to_lessons(lessons: list[dict[str, Any]], payload: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    start_date = _parse_date(payload.get("semesterStartDate") or payload.get("semester_start_date"))
    end_date = _parse_date(payload.get("semesterEndDate") or payload.get("semester_end_date"))
    meetings = _normalize_availability_windows(payload.get("classMeetings") or payload.get("class_meetings")) if payload.get("classMeetings") or payload.get("class_meetings") else []
    if not lessons or not start_date or not end_date or not meetings:
        return lessons, None
    if end_date < start_date:
        raise ValueError("semesterEndDate must be after semesterStartDate")

    class_dates = _class_dates_between(start_date, end_date, meetings)
    if not class_dates:
        return lessons, None

    dated_lessons: list[dict[str, Any]] = []
    for index, lesson in enumerate(lessons):
        meeting_date = class_dates[min(index, len(class_dates) - 1)]
        next_date = class_dates[index + 1] if index + 1 < len(class_dates) else None
        end_for_lesson = (next_date - timedelta(days=1)) if next_date else meeting_date
        dated_lessons.append({
            **lesson,
            "starts_on": lesson.get("starts_on") or lesson.get("startsOn") or meeting_date.isoformat(),
            "ends_on": lesson.get("ends_on") or lesson.get("endsOn") or end_for_lesson.isoformat(),
        })

    return dated_lessons, {
        "semesterStartDate": start_date.isoformat(),
        "semesterEndDate": end_date.isoformat(),
        "classMeetings": meetings,
        "classDateCount": len(class_dates),
    }


def _semester_window_from_payload(payload: dict[str, Any]) -> tuple[date | None, date | None]:
    start_date = _parse_date(payload.get("semesterStartDate") or payload.get("semester_start_date"))
    end_date = _parse_date(payload.get("semesterEndDate") or payload.get("semester_end_date"))
    return start_date, end_date


async def _list_latest_semester_windows(
    pool: asyncpg.Pool,
    user_id: str,
    *,
    exclude_course_id: str | None = None,
) -> list[dict[str, Any]]:
    query = """
        SELECT DISTINCT ON (subject_id) subject_id, parsed_json
        FROM course_syllabi
        WHERE user_id = $1
          AND ($2::text IS NULL OR subject_id <> $2)
        ORDER BY subject_id, created_at DESC
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, user_id, exclude_course_id)

    windows: list[dict[str, Any]] = []
    for row in rows:
        parsed = _json_value(row["parsed_json"], {})
        calendar = parsed.get("calendar") if isinstance(parsed, dict) else None
        if not isinstance(calendar, dict):
            continue
        start_date = _parse_date(calendar.get("semesterStartDate") or calendar.get("semester_start_date"))
        end_date = _parse_date(calendar.get("semesterEndDate") or calendar.get("semester_end_date"))
        if not start_date or not end_date or end_date < start_date:
            continue
        windows.append({
            "courseId": row["subject_id"],
            "startDate": start_date,
            "endDate": end_date,
        })
    return windows


def _max_semester_overlap(windows: list[dict[str, Any]]) -> tuple[int, date | None]:
    events: dict[date, int] = {}
    for window in windows:
        start_date = window.get("startDate")
        end_date = window.get("endDate")
        if not start_date or not end_date:
            continue
        events[start_date] = events.get(start_date, 0) + 1
        next_day = end_date + timedelta(days=1)
        events[next_day] = events.get(next_day, 0) - 1

    active = 0
    max_active = 0
    breach_day: date | None = None
    for current_day in sorted(events):
        active += events[current_day]
        if active > max_active:
            max_active = active
            breach_day = current_day
    return max_active, breach_day


def _class_dates_between(start_date: date, end_date: date, meetings: list[dict[str, str]]) -> list[date]:
    meeting_days = {item["day"] for item in meetings}
    cursor = start_date
    dates: list[date] = []
    while cursor <= end_date:
        if cursor.strftime("%a") in meeting_days:
            dates.append(cursor)
        cursor += timedelta(days=1)
    return dates


def _lesson_status(lesson: dict[str, Any], index: int, current_week: int | None, current_lesson_number: int | None) -> str:
    starts_on = _parse_date(lesson.get("startsOn") or lesson.get("starts_on"))
    if starts_on and current_week is None and current_lesson_number is None:
        if starts_on > date.today():
            return "future"
        ends_on = _parse_date(lesson.get("endsOn") or lesson.get("ends_on"))
        next_cutoff = ends_on or starts_on
        return "current" if next_cutoff >= date.today() else "taught"
    if current_week is None and current_lesson_number is None:
        return "current" if index == 0 else "future"
    lesson_week = _int_or_none(lesson.get("week_number")) or index + 1
    lesson_no = _int_or_none(lesson.get("lesson_number")) or index + 1
    if current_week is not None:
        if lesson_week < current_week:
            return "taught"
        if lesson_week > current_week:
            return "future"
    if current_lesson_number is not None:
        if lesson_no < current_lesson_number:
            return "taught"
        if lesson_no > current_lesson_number:
            return "future"
    return "current"


def _topic_from_syllabus_lesson(
    course_id: str,
    user_id: str,
    lesson_id: str,
    lesson: dict[str, Any],
    status: str,
    index: int,
) -> dict[str, Any]:
    readings = [str(value).strip() for value in (lesson.get("assigned_readings") or []) if str(value).strip()]
    title = (readings[0] if readings else str(lesson.get("title") or f"Lesson {index + 1}")).strip()
    description_parts = [str(lesson.get("title") or "").strip(), str(lesson.get("description") or "").strip()]
    if readings:
        description_parts.append("Readings: " + "; ".join(readings))
    description = "\n".join(part for part in description_parts if part)
    key = re.sub(r"[^a-zA-Z0-9]+", "-", f"{index + 1}-{title}".lower()).strip("-")[:60]
    parent_title = title[:120]
    return {
        "id": f"topic-{course_id}-syllabus-{key or index + 1}",
        "subject_id": course_id,
        "user_id": user_id,
        "title": _syllabus_topic_title(lesson, index),
        "description": description,
        "section_number": int(lesson.get("lesson_number") or index + 1),
        "content_chunk": description,
        "order_idx": int(lesson.get("order_idx") or index),
        "cost_mins": 30,
        "mastery": 0.05,
        "p_l0": 0.05,
        "p_t": 0.2,
        "p_g": 0.2,
        "p_s": 0.1,
        "awaiting_diagnostic": status in {"taught", "current"},
        "fsrs_card": {},
        "fsrs_stability": 0.0,
        "fsrs_difficulty": 5.0,
        "fsrs_last_review": None,
        "fsrs_due_date": None,
        "merged_from": [],
        "is_learned": False,
        "parent_topic_id": _parent_topic_id(course_id, _syllabus_parent_title(lesson, parent_title)),
        "parent_topic_title": _syllabus_parent_title(lesson, parent_title),
        "is_subtopic": True,
        "lesson_id": lesson_id,
        "learning_state": status,
        "practice_allowed": status in {"taught", "current"},
    }

def _is_syllabus_topic_id(course_id: str, topic_id: str) -> bool:
    topic_id = str(topic_id or "")
    return topic_id.startswith(f"topic-{course_id}-syllabus-") or topic_id.startswith(f"topic-{course_id}-chapter-")

async def _repair_syllabus_lessons_from_parsed(conn: asyncpg.Connection, course_id: str, user_id: str) -> None:
    syllabus = await conn.fetchrow(
        """SELECT id, parsed_json FROM course_syllabi
           WHERE subject_id=$1 AND user_id=$2 AND status <> 'skipped'
           ORDER BY created_at DESC LIMIT 1""",
        course_id,
        user_id,
    )
    if not syllabus:
        return
    parsed = _json_value(syllabus["parsed_json"], {})
    raw_lessons = parsed.get("lessons") or parsed.get("normalizedLessons") or []
    if not isinstance(raw_lessons, list) or not raw_lessons:
        return
    _mode, lessons, _normalized = parse_syllabus_payload({"mode": "manual", "lessons": raw_lessons})
    if not lessons:
        return
    for lesson in lessons:
        await conn.execute(
            """UPDATE syllabus_lessons
               SET title=$4, description=$5, assigned_readings=$6
               WHERE syllabus_id=$1 AND subject_id=$2 AND order_idx=$3""",
            syllabus["id"],
            course_id,
            int(lesson.get("order_idx") or 0),
            lesson.get("title") or "",
            lesson.get("description") or "",
            lesson.get("assigned_readings") or [],
        )
    patched = {**parsed, "normalizedLessons": lessons}
    await conn.execute(
        "UPDATE course_syllabi SET parsed_json=$3::jsonb WHERE id=$1 AND user_id=$2",
        syllabus["id"],
        user_id,
        patched,
    )

async def _sync_chapter_topics_from_syllabus(conn: asyncpg.Connection, course_id: str, user_id: str, lessons: list[asyncpg.Record]) -> None:
    syllabus = await conn.fetchrow(
        """SELECT parsed_json FROM course_syllabi
           WHERE subject_id=$1 AND user_id=$2 AND status <> 'skipped'
           ORDER BY created_at DESC LIMIT 1""",
        course_id,
        user_id,
    )
    parsed = _json_value(syllabus["parsed_json"], {}) if syllabus else {}
    chapters = parsed.get("chapters") if isinstance(parsed, dict) else None
    if not isinstance(chapters, list) or not chapters:
        await _sync_syllabus_topics_for_lessons(conn, course_id, user_id, lessons)
        return

    await conn.execute(
        """DELETE FROM topics
           WHERE subject_id=$1 AND user_id=$2 AND (id LIKE $3 OR id LIKE $4)""",
        course_id,
        user_id,
        f"topic-{course_id}-syllabus-%",
        f"topic-{course_id}-chapter-%",
    )
    for index, raw_chapter in enumerate(chapters):
        chapter = _normalize_syllabus_chapter(raw_chapter, index)
        if not chapter:
            continue
        lesson = _first_lesson_for_chapter(chapter, lessons, index)
        lesson_id = lesson["id"] if lesson else None
        status = str(lesson["status"] or "future") if lesson else "future"
        chapter_number = int(chapter["chapterNumber"])
        parent_id = f"topic-{course_id}-chapter-{chapter_number}"
        parent_title = _chapter_topic_title(chapter_number, str(chapter["title"]))
        description_parts = [parent_title, *chapter["sections"]]
        parent_topic = _base_syllabus_topic(
            course_id,
            user_id,
            parent_id,
            parent_title,
            "\n".join(part for part in description_parts if part),
            chapter_number,
            chapter_number,
            lesson_id,
            status,
            False,
            None,
            None,
        )
        await _upsert_syllabus_topic(conn, parent_topic)
        for section_index, section in enumerate(chapter["sections"], start=1):
            section_lesson = _lesson_for_chapter_section(chapter, section, lessons, index, section_index)
            section_lesson_id = section_lesson["id"] if section_lesson else lesson_id
            section_status = str(section_lesson["status"] or status) if section_lesson else status
            section_topic = _base_syllabus_topic(
                course_id,
                user_id,
                f"topic-{course_id}-chapter-{chapter_number}-section-{section_index}",
                section,
                f"{parent_title}\n{section}",
                chapter_number,
                chapter_number * 100 + section_index,
                section_lesson_id,
                section_status,
                True,
                parent_id,
                parent_title,
            )
            await _upsert_syllabus_topic(conn, section_topic)


async def _sync_syllabus_topics_for_lessons(conn: asyncpg.Connection, course_id: str, user_id: str, lessons: list[asyncpg.Record]) -> None:
    for index, lesson in enumerate(lessons):
        topic = _topic_from_syllabus_lesson(course_id, user_id, lesson["id"], dict(lesson), lesson["status"], index)
        existing = await conn.fetchval(
            """SELECT id FROM topics
               WHERE subject_id=$1 AND user_id=$2 AND id LIKE $3 AND order_idx=$4
               ORDER BY id LIMIT 1""",
            course_id,
            user_id,
            f"topic-{course_id}-syllabus-%",
            int(lesson["order_idx"] or index),
        )
        if not existing:
            await conn.execute(
                """INSERT INTO topics (id, subject_id, user_id, title, description, section_number, content_chunk, order_idx,
                                        cost_mins, mastery, p_l0, p_t, p_g, p_s, awaiting_diagnostic, fsrs_card,
                                        fsrs_stability, fsrs_difficulty, fsrs_last_review, fsrs_due_date, merged_from, is_learned,
                                        parent_topic_id, parent_topic_title, is_subtopic, lesson_id, learning_state, practice_allowed)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24,$25,$26,$27,$28)
                   ON CONFLICT (id) DO UPDATE SET
                     lesson_id=EXCLUDED.lesson_id,
                     title=EXCLUDED.title,
                     description=EXCLUDED.description,
                     content_chunk=EXCLUDED.content_chunk,
                     parent_topic_id=EXCLUDED.parent_topic_id,
                     parent_topic_title=EXCLUDED.parent_topic_title,
                     learning_state=EXCLUDED.learning_state,
                     practice_allowed=EXCLUDED.practice_allowed""",
                topic["id"], topic["subject_id"], topic["user_id"], topic["title"], topic["description"], topic["section_number"],
                topic["content_chunk"], topic["order_idx"], topic["cost_mins"], topic["mastery"], topic["p_l0"], topic["p_t"],
                topic["p_g"], topic["p_s"], topic["awaiting_diagnostic"], topic["fsrs_card"], topic["fsrs_stability"],
                topic["fsrs_difficulty"], topic["fsrs_last_review"], topic["fsrs_due_date"], topic["merged_from"], topic["is_learned"],
                topic.get("parent_topic_id"), topic.get("parent_topic_title"), topic.get("is_subtopic", True),
                topic["lesson_id"], topic["learning_state"], topic["practice_allowed"],
            )
        description_parts = [str(lesson["title"] or "").strip(), str(lesson["description"] or "").strip()]
        readings = [str(value).strip() for value in (lesson["assigned_readings"] or []) if str(value).strip()]
        if readings:
            description_parts.append("Readings: " + "; ".join(readings))
        description = "\n".join(part for part in description_parts if part)
        parent_title = _syllabus_parent_title(dict(lesson), str(lesson["title"] or f"Lesson {index + 1}"))
        await conn.execute(
            """UPDATE topics SET lesson_id=$3, title=$4, description=$5, content_chunk=$5,
                   parent_topic_id=$6, parent_topic_title=$7, learning_state=$8, practice_allowed=$9
               WHERE subject_id=$1 AND user_id=$2 AND id LIKE $10 AND order_idx=$11""",
            course_id,
            user_id,
            lesson["id"],
            _syllabus_topic_title(dict(lesson), index),
            description,
            _parent_topic_id(course_id, parent_title),
            parent_title,
            lesson["status"],
            lesson["status"] in {"taught", "current"},
            f"topic-{course_id}-syllabus-%",
            int(lesson["order_idx"] or index),
        )


def _normalize_syllabus_chapter(raw_chapter: Any, index: int) -> dict[str, Any] | None:
    if not isinstance(raw_chapter, dict):
        return None
    number = _int_or_none(
        raw_chapter.get("chapterNumber")
        or raw_chapter.get("chapter_number")
        or raw_chapter.get("number")
        or raw_chapter.get("chapter")
    ) or index + 1
    title = str(raw_chapter.get("title") or raw_chapter.get("name") or "").strip()
    if not title:
        return None
    sections = raw_chapter.get("sections") or raw_chapter.get("subtopics") or []
    if isinstance(sections, str):
        sections = [sections]
    if not sections:
        sections = []
        raw_lessons = raw_chapter.get("lessons") or []
        if isinstance(raw_lessons, list):
            for l in raw_lessons:
                if isinstance(l, dict):
                    ltitle = l.get("title") or l.get("name")
                else:
                    ltitle = str(l)
                if ltitle and str(ltitle).strip():
                    sections.append(str(ltitle).strip())
    weeks = raw_chapter.get("coveredInWeeks") or raw_chapter.get("covered_in_weeks") or raw_chapter.get("weeks") or []
    if isinstance(weeks, (str, int)):
        weeks = [weeks]
    return {
        "chapterNumber": int(number),
        "title": title,
        "sections": [str(section).strip() for section in sections if str(section).strip()],
        "coveredInWeeks": [week for week in (_int_or_none(value) for value in weeks) if week is not None],
    }


def _chapter_topic_title(chapter_number: int, title: str) -> str:
    raw_title = str(title or "").strip()
    if re.match(r"(?i)^\s*(?:ch\u01b0\u01a1ng|chuong|chapter)\s+[0-9ivxlcdm]+\b", raw_title):
        return raw_title[:120]
    return f"Ch\u01b0\u01a1ng {chapter_number} - {raw_title}"[:120]


def _first_lesson_for_chapter(chapter: dict[str, Any], lessons: list[asyncpg.Record], index: int) -> asyncpg.Record | None:
    if not lessons:
        return None
    weeks = {value for value in (_int_or_none(item) for item in (chapter.get("coveredInWeeks") or [])) if value is not None}
    if weeks:
        for lesson in lessons:
            if _int_or_none(lesson["week_number"]) in weeks or _int_or_none(lesson["lesson_number"]) in weeks:
                return lesson
    chapter_number = int(chapter.get("chapterNumber") or index + 1)
    chapter_terms = {f"chuong {chapter_number}", f"chapter {chapter_number}"}
    roman = _roman_numeral(chapter_number)
    if roman:
        chapter_terms.add(f"chapter {roman}")
    for lesson in lessons:
        haystack = normalize_for_search(
            " ".join(
                [
                    str(lesson["title"] or ""),
                    str(lesson["description"] or ""),
                    " ".join(str(value) for value in (lesson["assigned_readings"] or [])),
                ]
            )
        )
        if any(term in haystack for term in chapter_terms):
            return lesson
    return lessons[min(index, len(lessons) - 1)]


def _lesson_for_chapter_section(
    chapter: dict[str, Any],
    section: str,
    lessons: list[asyncpg.Record],
    chapter_index: int,
    section_index: int,
) -> asyncpg.Record | None:
    if not lessons:
        return None
    chapter_number = int(chapter.get("chapterNumber") or chapter_index + 1)
    section_text = str(section or "")
    section_ids = set(re.findall(r"\b\d+(?:\.\d+)*\b", section_text))
    section_haystack = normalize_for_search(section_text)
    chapter_lessons = [_lesson for _lesson in lessons if _lesson_mentions_chapter(_lesson, chapter_number)]
    search_lessons = chapter_lessons or lessons
    if not section_ids and chapter_lessons:
        return chapter_lessons[min(section_index - 1, len(chapter_lessons) - 1)]

    best: tuple[asyncpg.Record | None, float] = (None, 0.0)
    for lesson in search_lessons:
        lesson_text = " ".join(
            [
                str(lesson["title"] or ""),
                str(lesson["description"] or ""),
                " ".join(str(value) for value in (lesson["assigned_readings"] or [])),
            ]
        )
        normalized = normalize_for_search(lesson_text)
        score = 0.0
        if section_ids and section_ids & set(re.findall(r"\b\d+(?:\.\d+)*\b", lesson_text)):
            score += 2.0
        section_terms = [term for term in re.findall(r"[a-z0-9][a-z0-9_\-]{3,}", section_haystack) if term not in {"chuong", "chapter"}]
        if section_terms:
            hits = sum(1 for term in section_terms[:12] if term in normalized)
            score += hits / max(1, min(len(section_terms), 12))
        if score > best[1]:
            best = (lesson, score)
    if best[0] is not None and best[1] >= 1.5:
        return best[0]
    if chapter_lessons:
        return chapter_lessons[min(section_index - 1, len(chapter_lessons) - 1)]
    return _first_lesson_for_chapter(chapter, lessons, chapter_index)


def _lesson_mentions_chapter(lesson: asyncpg.Record, chapter_number: int) -> bool:
    for reading in lesson["assigned_readings"] or []:
        if _chapter_number_from_text(str(reading or "")) == chapter_number:
            return True
    haystack = normalize_for_search(
        " ".join(
            [
                str(lesson["title"] or ""),
                str(lesson["description"] or ""),
                " ".join(str(value) for value in (lesson["assigned_readings"] or [])),
            ]
        )
    )
    terms = {f"chuong {chapter_number}", f"chapter {chapter_number}"}
    roman = _roman_numeral(chapter_number)
    if roman:
        terms.add(f"chapter {roman}")
    return any(term in haystack for term in terms)


def _chapters_from_lessons(lessons: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chapters: dict[int, dict[str, Any]] = {}
    chapter_text_to_num: dict[str, int] = {}
    for lesson in lessons:
        readings = [str(value).strip() for value in (lesson.get("assigned_readings") or lesson.get("assignedReadings") or []) if str(value).strip()]
        chapter_number = None
        chapter_label = ""
        for reading in readings:
            chapter_number = _chapter_number_from_text(reading)
            if chapter_number is not None:
                chapter_label = reading
                break
        
        lesson_ch = str(lesson.get("chapter") or "").strip()
        if chapter_number is None and lesson_ch:
            chapter_number = _chapter_number_from_text(lesson_ch)
            if chapter_number is not None:
                chapter_label = lesson_ch
                
        lesson_title = str(lesson.get("title") or "").strip()
        if chapter_number is None and lesson_title:
            chapter_number = _chapter_number_from_text(lesson_title)
            if chapter_number is not None:
                chapter_label = lesson_title
                
        if chapter_number is None:
            ch_key = lesson_ch or lesson_title or "Uncategorized"
            if ch_key not in chapter_text_to_num:
                next_num = 1
                while next_num in chapters or next_num in chapter_text_to_num.values():
                    next_num += 1
                chapter_text_to_num[ch_key] = next_num
            chapter_number = chapter_text_to_num[ch_key]
            chapter_label = ch_key

        chapter = chapters.setdefault(
            chapter_number,
            {"chapterNumber": chapter_number, "title": chapter_label or f"Chương {chapter_number}", "sections": [], "coveredInWeeks": []},
        )
        week = _int_or_none(lesson.get("week_number") or lesson.get("weekNumber"))
        if week is not None and week not in chapter["coveredInWeeks"]:
            chapter["coveredInWeeks"].append(week)
        sections = lesson.get("sections") or []
        if isinstance(sections, str):
            sections = [sections]
        section_values = [str(section).strip() for section in sections if str(section).strip()]
        if not section_values:
            section_values = [str(lesson.get("title") or "").strip()]
        for section in section_values:
            if section and section not in chapter["sections"]:
                chapter["sections"].append(section)
    return [chapters[key] for key in sorted(chapters)]


def _chapter_number_from_text(value: str) -> int | None:
    direct = re.search(r"(?i)\b(?:chương|chuong|chapter)\s*([0-9]+|[ivxlcdm]+)\b", str(value or ""))
    if direct:
        token = direct.group(1).lower()
        return int(token) if token.isdigit() else _roman_to_int(token)
    text = normalize_for_search(value)
    match = re.search(r"\b(?:chuong|chapter)\s+([0-9]+|[ivxlcdm]+)\b", text)
    if not match:
        return None
    token = match.group(1)
    if token.isdigit():
        return int(token)
    return _roman_to_int(token)


def _roman_to_int(value: str) -> int | None:
    values = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}
    total = 0
    previous = 0
    for char in reversed(str(value or "").lower()):
        current = values.get(char)
        if current is None:
            return None
        if current < previous:
            total -= current
        else:
            total += current
            previous = current
    return total or None


def _roman_numeral(value: int) -> str:
    numerals = [
        (1000, "m"),
        (900, "cm"),
        (500, "d"),
        (400, "cd"),
        (100, "c"),
        (90, "xc"),
        (50, "l"),
        (40, "xl"),
        (10, "x"),
        (9, "ix"),
        (5, "v"),
        (4, "iv"),
        (1, "i"),
    ]
    result = ""
    remainder = int(value or 0)
    for number, numeral in numerals:
        while remainder >= number:
            result += numeral
            remainder -= number
    return result


def _base_syllabus_topic(
    course_id: str,
    user_id: str,
    topic_id: str,
    title: str,
    description: str,
    section_number: int,
    order_idx: int,
    lesson_id: str | None,
    status: str,
    is_subtopic: bool,
    parent_topic_id: str | None,
    parent_topic_title: str | None,
) -> dict[str, Any]:
    return {
        "id": topic_id,
        "subject_id": course_id,
        "user_id": user_id,
        "title": title[:120],
        "description": description,
        "section_number": section_number,
        "content_chunk": description,
        "order_idx": order_idx,
        "cost_mins": 30,
        "mastery": 0.05,
        "p_l0": 0.05,
        "p_t": 0.2,
        "p_g": 0.2,
        "p_s": 0.1,
        "awaiting_diagnostic": status in {"taught", "current"},
        "fsrs_card": {},
        "fsrs_stability": 0.0,
        "fsrs_difficulty": 5.0,
        "fsrs_last_review": None,
        "fsrs_due_date": None,
        "merged_from": [],
        "is_learned": False,
        "parent_topic_id": parent_topic_id,
        "parent_topic_title": parent_topic_title,
        "is_subtopic": is_subtopic,
        "lesson_id": lesson_id,
        "learning_state": status,
        "practice_allowed": status in {"taught", "current"},
    }


async def _upsert_syllabus_topic(conn: asyncpg.Connection, topic: dict[str, Any]) -> None:
    await conn.execute(
        """INSERT INTO topics (id, subject_id, user_id, title, description, section_number, content_chunk, order_idx,
                                cost_mins, mastery, p_l0, p_t, p_g, p_s, awaiting_diagnostic, fsrs_card,
                                fsrs_stability, fsrs_difficulty, fsrs_last_review, fsrs_due_date, merged_from, is_learned,
                                parent_topic_id, parent_topic_title, is_subtopic, lesson_id, learning_state, practice_allowed)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24,$25,$26,$27,$28)
           ON CONFLICT (id) DO UPDATE SET
             title=EXCLUDED.title,
             description=EXCLUDED.description,
             content_chunk=EXCLUDED.content_chunk,
             order_idx=EXCLUDED.order_idx,
             parent_topic_id=EXCLUDED.parent_topic_id,
             parent_topic_title=EXCLUDED.parent_topic_title,
             is_subtopic=EXCLUDED.is_subtopic,
             lesson_id=EXCLUDED.lesson_id,
             learning_state=EXCLUDED.learning_state,
             practice_allowed=EXCLUDED.practice_allowed""",
        topic["id"], topic["subject_id"], topic["user_id"], topic["title"], topic["description"], topic["section_number"],
        topic["content_chunk"], topic["order_idx"], topic["cost_mins"], topic["mastery"], topic["p_l0"], topic["p_t"],
        topic["p_g"], topic["p_s"], topic["awaiting_diagnostic"], topic["fsrs_card"], topic["fsrs_stability"],
        topic["fsrs_difficulty"], topic["fsrs_last_review"], topic["fsrs_due_date"], topic["merged_from"], topic["is_learned"],
        topic.get("parent_topic_id"), topic.get("parent_topic_title"), topic.get("is_subtopic", True),
        topic.get("lesson_id"), topic["learning_state"], topic["practice_allowed"],
    )


def _syllabus_parent_title(lesson: dict[str, Any], fallback: str) -> str:
    readings = [str(value).strip() for value in (lesson.get("assigned_readings") or lesson.get("assignedReadings") or []) if str(value).strip()]
    return (readings[0] if readings else fallback).strip()[:120]

def _syllabus_topic_title(lesson: dict[str, Any], index: int) -> str:
    parent = _syllabus_parent_title(lesson, str(lesson.get("title") or f"Lesson {index + 1}"))
    raw_title = str(lesson.get("title") or f"Lesson {index + 1}").strip()
    detail = re.sub(rf"^\s*{re.escape(parent)}\s*[:\-–—]?\s*", "", raw_title, flags=re.IGNORECASE).strip()
    title = f"{parent} - {detail}" if detail and detail.lower() != parent.lower() else parent
    return title[:120]

def _best_lesson_match(lessons: list[asyncpg.Record], text: str) -> tuple[asyncpg.Record | None, float, str]:
    best: tuple[asyncpg.Record | None, float, str] = (None, 0.0, "No lessons.")
    for lesson in lessons:
        score, reason = score_lesson_match(dict(lesson), text)
        if score > best[1]:
            best = (lesson, score, reason)
    return best


async def _sync_topic_learning_states(pool: asyncpg.Pool, course_id: str, user_id: str) -> None:
    async with pool.acquire() as conn:
        active = await _course_has_active_syllabus(conn, course_id, user_id)
        if not active:
            await conn.execute(
                """UPDATE topics SET learning_state='taught', practice_allowed=true
                   WHERE subject_id=$1 AND user_id=$2""",
                course_id, user_id,
            )
            return
        await _sync_lesson_statuses_from_dates(conn, course_id, user_id)
        await conn.execute(
            """UPDATE topics t SET
                 learning_state = COALESCE(sl.status, 'future'),
                 practice_allowed = COALESCE(sl.status IN ('taught','current'), FALSE)
               FROM syllabus_lessons sl
               WHERE t.lesson_id=sl.id AND t.subject_id=$1 AND t.user_id=$2""",
            course_id, user_id,
        )
        await conn.execute(
            """UPDATE topics SET learning_state='future', practice_allowed=false
               WHERE subject_id=$1 AND user_id=$2 AND lesson_id IS NULL""",
            course_id, user_id,
        )

async def _sync_lesson_statuses_from_dates(conn: asyncpg.Connection, course_id: str, user_id: str) -> None:
    syllabus = await conn.fetchrow(
        """SELECT id, parsed_json FROM course_syllabi
           WHERE subject_id=$1 AND user_id=$2
           ORDER BY created_at DESC LIMIT 1""",
        course_id,
        user_id,
    )
    parsed = _json_value(syllabus["parsed_json"], {}) if syllabus else {}
    if not isinstance(parsed, dict) or not parsed.get("calendar"):
        return
    today = date.today()
    rows = await conn.fetch(
        """SELECT id, starts_on FROM syllabus_lessons
           WHERE subject_id=$1 AND starts_on IS NOT NULL
           ORDER BY order_idx""",
        course_id,
    )
    if not rows:
        return
    current = None
    for row in rows:
        if row["starts_on"] <= today:
            current = row
        else:
            break
    if current is None:
        # All lessons start in the future
        await conn.execute(
            """UPDATE syllabus_lessons SET status = 'future'
               WHERE subject_id=$1""",
            course_id,
        )
        await conn.execute(
            """UPDATE course_syllabi SET current_lesson_id = NULL, current_week = NULL
               WHERE subject_id=$1 AND user_id=$2""",
            course_id,
            user_id,
        )
        return

    await conn.execute(
        """UPDATE syllabus_lessons SET status = CASE
             WHEN order_idx < (SELECT order_idx FROM syllabus_lessons WHERE id=$2) THEN 'taught'
             WHEN id=$2 THEN 'current'
             ELSE 'future' END
           WHERE subject_id=$1""",
        course_id,
        current["id"],
    )
    await conn.execute(
        """UPDATE course_syllabi sy SET current_lesson_id=$2,
             current_week=(SELECT week_number FROM syllabus_lessons WHERE id=$2)
           WHERE sy.subject_id=$1 AND sy.user_id=$3""",
        course_id,
        current["id"],
        user_id,
    )

async def _course_has_active_syllabus(conn: asyncpg.Connection, course_id: str, user_id: str) -> bool:
    row = await conn.fetchrow(
        """SELECT sy.status,
                  EXISTS(SELECT 1 FROM syllabus_lessons sl WHERE sl.subject_id=sy.subject_id) AS has_lessons
           FROM course_syllabi sy
           WHERE sy.subject_id=$1 AND sy.user_id=$2
           ORDER BY sy.created_at DESC LIMIT 1""",
        course_id, user_id,
    )
    return bool(row and row["status"] != "skipped" and row["has_lessons"])


async def _has_active_syllabus(pool: asyncpg.Pool, course_id: str, user_id: str) -> bool:
    async with pool.acquire() as conn:
        return await _course_has_active_syllabus(conn, course_id, user_id)


async def _allowed_topic_ids(pool: asyncpg.Pool, course_id: str, user_id: str, include_current: bool = True) -> list[str]:
    statuses = ["taught", "current"] if include_current else ["taught"]
    async with pool.acquire() as conn:
        active = await _course_has_active_syllabus(conn, course_id, user_id)
        if not active:
            rows = await conn.fetch("SELECT id FROM topics WHERE subject_id=$1 AND user_id=$2", course_id, user_id)
        else:
            rows = await conn.fetch(
                "SELECT id FROM topics WHERE subject_id=$1 AND user_id=$2 AND (practice_allowed=true OR learning_state = ANY($3::text[]))",
                course_id, user_id, statuses,
            )
    return [row["id"] for row in rows]

async def _assert_topic_practice_allowed(pool: asyncpg.Pool, course_id: str | None, user_id: str, payload: dict[str, Any] | None = None) -> None:
    if not course_id:
        raise ValueError("courseId is required")
    course = await get_course(pool, course_id, user_id)
    if course.get("activeBehavior") == "exam_sprint":
        return
    topic_ids = []
    if (payload or {}).get("topicId"):
        topic_ids.append(str((payload or {})["topicId"]))
    if isinstance((payload or {}).get("topicIds"), list):
        topic_ids.extend(str(value) for value in (payload or {}).get("topicIds") or [])
    if not topic_ids:
        return
    allowed = set(await _allowed_topic_ids(pool, course_id, user_id))
    blocked = [topic_id for topic_id in topic_ids if topic_id not in allowed]
    if blocked:
        # Manual workspace practice can target future lessons even in continuous mode.
        # Scheduling remains gated in the scheduler and task APIs.
        return

async def _allowed_lesson_ids(pool: asyncpg.Pool, course_id: str, user_id: str) -> set[str]:
    statuses = ["taught", "current"]
    async with pool.acquire() as conn:
        active = await _course_has_active_syllabus(conn, course_id, user_id)
        if not active:
            return set()
        rows = await conn.fetch(
            "SELECT id, status, order_idx FROM syllabus_lessons WHERE subject_id=$1 ORDER BY order_idx",
            course_id,
        )
    allowed = {row["id"] for row in rows if row["status"] in statuses}
    return allowed

async def _mapped_chunk_ids_for_lessons(pool: asyncpg.Pool, lesson_ids: set[str]) -> set[str]:
    if not lesson_ids:
        return set()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT chunk_id FROM lesson_material_mappings WHERE lesson_id = ANY($1::text[]) AND chunk_id IS NOT NULL",
            list(lesson_ids),
        )
    return {row["chunk_id"] for row in rows}


async def _topic_titles(pool: asyncpg.Pool, topic_ids: list[str]) -> list[str]:
    if not topic_ids:
        return []
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT title FROM topics WHERE id = ANY($1::text[])", topic_ids)
    return [row["title"] for row in rows]


async def _filter_chunks_for_syllabus(pool: asyncpg.Pool, course_id: str, user_id: str, chunks: list[dict[str, Any]], payload: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    course = await get_course(pool, course_id, user_id)
    if course.get("activeBehavior") == "exam_sprint":
        return chunks
    has_syllabus = bool(course.get("syllabusStatus") and course.get("syllabusStatus") != "skipped")
    if not has_syllabus:
        return chunks
    await _assert_topic_practice_allowed(pool, course_id, user_id, payload or {})
    allowed_ids = set(await _allowed_topic_ids(pool, course_id, user_id))
    allowed_lessons = await _allowed_lesson_ids(pool, course_id, user_id)
    mapped_chunk_ids = await _mapped_chunk_ids_for_lessons(pool, allowed_lessons)
    requested_topic_ids = {
        str(value)
        for value in [*((payload or {}).get("topicIds") or []), *(([(payload or {}).get("topicId")] if (payload or {}).get("topicId") else []))]
        if value
    }
    if requested_topic_ids:
        requested_chunks = [
            chunk for chunk in chunks
            if any(topic_id in requested_topic_ids for topic_id in chunk.get("topicIds") or [])
        ]
        if requested_chunks:
            return requested_chunks
    filtered = [
        chunk for chunk in chunks
        if chunk.get("id") in mapped_chunk_ids
        or any(topic_id in allowed_ids for topic_id in chunk.get("topicIds") or [])
    ]
    return filtered if filtered else []


def _int_or_none(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except Exception:
        return None


async def _get_thread(pool: asyncpg.Pool, thread_id: str | None, user_id: str) -> dict[str, Any] | None:
    if not thread_id:
        return None
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM chat_threads WHERE id=$1 AND user_id=$2", thread_id, user_id)
    return _thread_from_row(row) if row else None


async def _insert_message(pool: asyncpg.Pool, thread_id: str, user_id: str, role: str, content: str, refs: list[dict[str, Any]], actions: list[dict[str, Any]]) -> dict[str, Any]:
    message_id = f"msg_{uuid.uuid4().hex[:10]}"
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO chat_messages (id, thread_id, user_id, role, content, source_refs, actions) VALUES ($1,$2,$3,$4,$5,$6,$7)",
            message_id,
            thread_id,
            user_id,
            role,
            content,
            refs,
            actions,
        )
        row = await conn.fetchrow("SELECT * FROM chat_messages WHERE id=$1", message_id)
    return _message_from_row(row)


async def _fallback_plain_chat_completion(message: str, history: list[dict[str, str]]) -> str:
    try:
        from app.config import settings
        from app.core.document.llm_section_split import get_openai_client

        client = get_openai_client()
        messages = [{"role": "system", "content": "Bạn là trợ lý học tập. Hãy trả lời bằng tiếng Việt."}]
        for item in history or []:
            messages.append({"role": item.get("role", "user"), "content": item.get("content", "")})
        messages.append({"role": "user", "content": message})
        completion = client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=messages,
            temperature=0.5,
        )
        return completion.choices[0].message.content or ""
    except Exception as error:
        return f"Rất tiếc, đã xảy ra lỗi hệ thống: {error}"


async def _build_answer(pool: asyncpg.Pool, course_id: str, message: str, chunks: list[dict[str, Any]], refs: list[dict[str, Any]], has_selection: bool, user_id: str, history: list[dict[str, Any]] | None = None) -> str:
    if not chunks:
        sources = await list_sources(pool, course_id, user_id)
        if sources:
            return _clarifying_question(message, bool(sources), has_selection)
        return await _general_llm_answer(message, history)

    context = _rag_context(chunks[:6])
    try:
        answer = await _rag_llm_answer(message, context, history)
    except Exception:
        return _clarifying_question(message, True, has_selection)

    if not answer:
        return _clarifying_question(message, True, has_selection)
    if refs and not re.search(r"\[\d+\]", answer) and not answer.strip().endswith("?"):
        answer = f"{answer.rstrip()} [1]"
    return answer

async def _rag_llm_answer(message: str, context: str, history: list[dict[str, Any]] | None = None) -> str:
    history_history = history or []
    return await _run_blocking(
        complete_text,
        [
            {
                "role": "system",
                "content": RAG_TUTOR_SYSTEM_PROMPT,
            },
            *history_history,
            {
                "role": "user",
                "content": f"Question:\n{message}\n\nSource excerpts:\n{context}",
            },
        ],
        0.2,
        900,
    )

async def _general_llm_answer(message: str, history: list[dict[str, Any]] | None = None) -> str:
    history_history = history or []
    try:
        return await _run_blocking(
            complete_text,
            [
                {"role": "system", "content": GENERAL_TUTOR_SYSTEM_PROMPT},
                *history_history,
                {"role": "user", "content": message},
            ],
            0.3,
            700,
        )
    except Exception:
        return _general_answer(message)

async def _run_blocking(func, *args):
    import asyncio
    return await asyncio.to_thread(func, *args)

def _rag_context(chunks: list[dict[str, Any]]) -> str:
    lines = []
    for index, chunk in enumerate(chunks, start=1):
        page = chunk.get("pageStart") or chunk.get("page")
        source = chunk.get("filename") or chunk.get("sourceId") or "source"
        section = chunk.get("sectionPath") or chunk.get("sectionTitle") or chunk.get("topicName") or ""
        text = re.sub(r"\s+", " ", str(chunk.get("citationText") or chunk.get("quote") or chunk.get("text") or "")).strip()
        lines.append(f"[{index}] {source}; page={page or 'n/a'}; section={section}\n{text[:1800]}")
    return "\n\n".join(lines)

def _clarifying_question(message: str, has_sources: bool, has_selection: bool) -> str:
    if has_selection or has_sources:
        return "Không tìm thấy thông tin đủ rõ trong các tài liệu đang được chọn. Bạn có thể chọn thêm tài liệu liên quan hoặc kiểm tra lại câu hỏi."
    return _general_answer(message)
    target = "tài liệu đã chọn" if has_selection else "tài liệu của môn học" if has_sources else "câu hỏi"
    if "trang" not in normalize_for_search(message) and has_sources:
        return f"Mình chưa chắc phần nào trong {target} bạn muốn hỏi. Bạn có thể cho mình biết chương, trang, hoặc khái niệm cụ thể hơn không?"
    return f"Mình chưa chắc ý bạn trong {target}. Bạn muốn mình làm rõ khía cạnh nào?"


async def _build_quiz_questions(course: dict[str, Any], chunks: list[dict[str, Any]], count: int, topic_id: str | None = None, payload: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    fallback = _fallback_quiz_questions(course, chunks, count, topic_id)
    if chunks:
        try:
            data = await _run_blocking(
                complete_json,
                "Create multiple-choice quiz questions from study context. Return JSON only.",
                (
                    "Return exactly this shape: "
                    "{\"questions\":[{\"question\":string,\"options\":[string,string,string,string],"
                    "\"correctAnswer\":string,\"explanation\":string,\"citationIndex\":number}]}.\n"
                    f"Course: {course['name']}\n"
                    f"Difficulty: {(payload or {}).get('difficulty') or 'medium'}\n"
                    f"User requirements: {(payload or {}).get('instructions') or (payload or {}).get('query') or 'Cover the selected sources broadly.'}\n"
                    f"Context:\n{_rag_context(chunks)}\n\nCreate {count} questions. correctAnswer must exactly match one option."
                ),
                0.15,
            )
            questions = data.get("questions", []) if isinstance(data, dict) else []
            if questions:
                return _normalize_quiz_questions(course, chunks, questions, fallback, count, topic_id)
        except Exception:
            pass
    return fallback


def _fallback_quiz_questions(course: dict[str, Any], chunks: list[dict[str, Any]], count: int, topic_id: str | None = None) -> list[dict[str, Any]]:
    base = chunks or [{"topicName": course["name"], "quote": f"Review core ideas for {course['name']}.", "text": course["name"]}]
    questions = []
    for index in range(count):
        chunk = base[index % len(base)]
        correct = chunk.get("quote") or str(chunk.get("text") or "")[:140] or course["name"]
        questions.append({
            "id": f"question_{uuid.uuid4().hex[:10]}",
            "question": f"Which statement is supported by the source about {chunk.get('topicName') or course['name']}?",
            "options": [correct, "The source says this topic can be skipped.", "The source contradicts the main definition.", "The source contains no useful detail."],
            "correctAnswer": correct,
            "explanation": correct,
            "topicId": topic_id or (chunk.get("topicIds") or [None])[0],
            "topicName": chunk.get("topicName") or course["name"],
            "sourceRef": source_ref_from_chunk(chunk) if chunk.get("sourceId") else None,
        })
    return questions


async def _build_flashcards(course: dict[str, Any], chunks: list[dict[str, Any]], count: int, topic_id: str | None = None) -> list[dict[str, Any]]:
    fallback = _fallback_flashcards(course, chunks, count, topic_id)
    if chunks:
        try:
            data = await _run_blocking(
                complete_json,
                "Create flashcards from study context. Return JSON only.",
                (
                    "Return exactly this shape: "
                    "{\"flashcards\":[{\"front\":string,\"back\":string,\"explanation\":string,\"citationIndex\":number}]}.\n"
                    f"Course: {course['name']}\nContext:\n{_rag_context(chunks)}\n\nCreate {count} flashcards."
                ),
                0.15,
            )
            cards = data.get("flashcards", []) if isinstance(data, dict) else []
            if cards:
                return _normalize_flashcards(course, chunks, cards, fallback, count, topic_id)
        except Exception:
            pass
    return fallback


def _fallback_flashcards(course: dict[str, Any], chunks: list[dict[str, Any]], count: int, topic_id: str | None = None) -> list[dict[str, Any]]:
    base = chunks or [{"topicName": course["name"], "quote": f"Review core ideas for {course['name']}.", "text": course["name"]}]
    cards = []
    for index in range(count):
        chunk = base[index % len(base)]
        cards.append({
            "front": f"Explain: {chunk.get('topicName') or course['name']}",
            "back": chunk.get("quote") or chunk.get("text") or f"Review {course['name']}.",
            "explanation": f"Generated from {chunk.get('filename') or 'course material'}.",
            "topicId": topic_id or (chunk.get("topicIds") or [None])[0],
            "sourceRef": source_ref_from_chunk(chunk) if chunk.get("sourceId") else None,
        })
    return cards


def _normalize_quiz_questions(course: dict[str, Any], chunks: list[dict[str, Any]], questions: list[dict[str, Any]], fallback: list[dict[str, Any]], count: int, topic_id: str | None) -> list[dict[str, Any]]:
    if not chunks:
        chunks = [{"topicName": course.get("name") or "Course", "quote": "Review course material.", "text": ""}]
    normalized = []
    for index, question in enumerate(questions[:count]):
        chunk = chunks[max(0, min(len(chunks) - 1, int(question.get("citationIndex") or index + 1) - 1))]
        options = question.get("options") if isinstance(question.get("options"), list) else []
        options = options[:4] if len(options) >= 2 else [question.get("correctAnswer") or chunk.get("quote") or course["name"], "Not enough information", "A distractor", "Another distractor"]
        correct = question.get("correctAnswer") if question.get("correctAnswer") in options else options[0]
        normalized.append({
            "id": f"question_{uuid.uuid4().hex[:10]}",
            "question": question.get("question") or f"What is a key idea from {chunk.get('topicName') or course['name']}?",
            "options": options,
            "correctAnswer": correct,
            "explanation": question.get("explanation") or chunk.get("quote") or "Based on the selected course material.",
            "topicId": topic_id or (chunk.get("topicIds") or [None])[0],
            "topicName": chunk.get("topicName") or course["name"],
            "sourceRef": source_ref_from_chunk(chunk) if chunk.get("sourceId") else None,
        })
    return (normalized + fallback)[:count]


def _normalize_flashcards(course: dict[str, Any], chunks: list[dict[str, Any]], cards: list[dict[str, Any]], fallback: list[dict[str, Any]], count: int, topic_id: str | None) -> list[dict[str, Any]]:
    if not chunks:
        chunks = [{"topicName": course.get("name") or "Course", "quote": "Review course material.", "text": ""}]
    normalized = []
    for index, card in enumerate(cards[:count]):
        chunk = chunks[max(0, min(len(chunks) - 1, int(card.get("citationIndex") or index + 1) - 1))]
        normalized.append({
            "front": card.get("front") or f"Explain: {chunk.get('topicName') or course['name']}",
            "back": card.get("back") or chunk.get("quote") or f"Review {course['name']}.",
            "explanation": card.get("explanation") or f"Generated from {chunk.get('filename') or 'course material'}.",
            "topicId": topic_id or (chunk.get("topicIds") or [None])[0],
            "sourceRef": source_ref_from_chunk(chunk) if chunk.get("sourceId") else None,
        })
    return (normalized + fallback)[:count]


def _course_from_row(row: asyncpg.Record) -> dict[str, Any]:
    mastery = round(float(_rget(row, "mastery_avg", 0) or 0) * 100)
    confidence = round(float(_rget(row, "confidence_avg", 0) or 0) * 100)
    source_count = int(_rget(row, "source_count", 0) or 0)
    status = "not_enough_data" if source_count == 0 else "behind" if mastery < 40 else "needs_attention" if mastery < 65 else "on_track"
    priority = _rget(row, "priority") or ("high" if _rget(row, "is_priority") else "medium")
    exam_date = _rget(row, "exam_date")
    sprint_starts = exam_date - timedelta(days=14) if exam_date else None
    active_behavior = "exam_sprint" if row["mode"] == "exam_sprint" or (exam_date and (exam_date - date.today()).days <= 14) else "continuous"
    return {
        "id": row["id"],
        "userId": row["user_id"],
        "name": row["name"],
        "mode": _subject_mode_to_course(row["mode"]),
        "targetScore": _rget(row, "target_score"),
        "examDate": _iso(exam_date),
        "priority": priority,
        "availability": list(_rget(row, "days_available", []) or []),
        "availabilityWindows": _json_value(_rget(row, "availability_windows"), []),
        "coverageWarning": _rget(row, "coverage_warning"),
        "status": status,
        "masteryPercent": mastery,
        "confidencePercent": confidence,
        "readinessPercent": mastery,
        "sourceCount": source_count,
        "topicCount": int(_rget(row, "topic_count", 0) or 0),
        "taskCount": int(_rget(row, "task_count", 0) or 0),
        "featured": bool(_rget(row, "featured", False)),
        "shared": bool(_rget(row, "shared", False)),
        "syllabusStatus": _rget(row, "syllabus_status"),
        "currentWeek": _rget(row, "current_week"),
        "currentLesson": {"id": _rget(row, "current_lesson_id"), "title": _rget(row, "current_lesson_title")} if _rget(row, "current_lesson_id") else None,
        "activeBehavior": active_behavior,
        "examSprintStartsAt": _iso(sprint_starts),
        "createdAt": _iso(_rget(row, "created_at")),
        "updatedAt": _iso(_rget(row, "updated_at")),
    }


def _source_from_row(row: asyncpg.Record) -> dict[str, Any]:
    return {
        "id": row["id"],
        "documentId": row["id"],
        "courseId": row["subject_id"],
        "filename": row["filename"],
        "originalName": row["original_name"] or row["filename"],
        "fileType": row["file_type"],
        "mimeType": row["mime_type"],
        "status": row["status"],
        "selected": row["selected"],
        "topicCount": row["topic_count"],
        "url": row["url"],
        "text": row["text_content"],
        "storagePath": row["storage_path"],
        "errorMessage": row["error_message"],
        "parsedAt": _iso(row["parsed_at"]),
        "uploadedAt": _iso(row["uploaded_at"]),
        "createdAt": _iso(row["created_at"]),
    }


def _topic_from_row(row: asyncpg.Record) -> dict[str, Any]:
    mastery = round(float(row["mastery"] or 0) * 100)
    confidence = float(_rget(row, "mastery_confidence", 0) or 0)
    learning_state = _rget(row, "learning_state", "taught") or "taught"
    practice_allowed = bool(_rget(row, "practice_allowed", True))
    is_due = bool(_rget(row, "fsrs_due_date") and _rget(row, "fsrs_due_date") <= date.today())
    availability_status = _topic_availability_status(learning_state, practice_allowed, mastery, is_due)
    parent_id = _rget(row, "parent_topic_id") or row["id"]
    parent_title = _rget(row, "parent_topic_title") or row["title"]
    parent_total = int(_rget(row, "parent_subtopic_count", 1) or 1)
    parent_available = int(_rget(row, "parent_available_count", 1 if practice_allowed else 0) or 0)
    topic_completion_state = _topic_completion_state(parent_total, parent_available)
    overall_mastery = round(float(_rget(row, "parent_mastery_avg", row["mastery"]) or 0) * 100)
    available_avg = _rget(row, "parent_available_mastery_avg")
    display_status = (
        "locked" if availability_status == "locked"
        else "weak" if mastery < 45
        else "needs_review" if mastery < 70 or availability_status == "review_due"
        else "good"
    )
    review_count = int(_rget(row, "review_count", 0) or 0)
    quiz_count = int(_rget(row, "quiz_count", 0) or 0)
    flashcard_count = int(_rget(row, "flashcard_count", 0) or 0)
    return {
        "id": row["id"],
        "courseId": row["subject_id"],
        "subjectId": row["subject_id"],
        "name": row["title"],
        "title": row["title"],
        "moduleName": f"Section {row['section_number'] or row['order_idx'] or 1}",
        "description": row["description"],
        "masteryPercent": mastery,
        "mastery": mastery,
        "masteryConfidence": confidence,
        "confidencePercent": round(confidence * 100),
        "masteryEvidenceSource": _rget(row, "mastery_evidence_source", "none") or "none",
        "importance": "high" if mastery < 50 else "medium",
        "status": display_status,
        "dueReviewAt": _iso(row["fsrs_due_date"]),
        "awaitingDiagnostic": bool(row["awaiting_diagnostic"]),
        "isLearned": bool(row["is_learned"]),
        "parentTopicId": parent_id,
        "parentTopicTitle": parent_title,
        "isSubtopic": bool(_rget(row, "is_subtopic", True)),
        "lessonId": _rget(row, "lesson_id"),
        "lessonTitle": _rget(row, "lesson_title") or _rget(row, "mapped_lesson_title"),
        "reviewCount": review_count,
        "quizCount": quiz_count,
        "hasQuiz": quiz_count > 0,
        "flashcardCount": flashcard_count,
        "hasFlashcard": flashcard_count > 0,
        "learningState": learning_state,
        "practiceAllowed": practice_allowed,
        "availabilityStatus": availability_status,
        "topicCompletionState": topic_completion_state,
        "overallMasteryPercent": overall_mastery,
        "availableMasteryPercent": round(float(available_avg) * 100) if available_avg is not None else None,
        "isPartialTopic": topic_completion_state == "partially_taught" and practice_allowed,
    }


def _topic_availability_status(learning_state: str, practice_allowed: bool, mastery: int, is_due: bool) -> str:
    if not practice_allowed and learning_state == "future":
        return "locked"
    if learning_state == "current":
        return "current"
    if is_due:
        return "review_due"
    if mastery >= 85:
        return "mastered"
    return "taught" if practice_allowed else "locked"


def _topic_completion_state(total_subtopics: int, available_subtopics: int) -> str:
    if available_subtopics <= 0:
        return "not_started"
    if available_subtopics < max(1, total_subtopics):
        return "partially_taught"
    return "fully_taught"


def _task_from_row(row: asyncpg.Record) -> dict[str, Any]:
    start_at = _rget(row, "start_at") or datetime.combine(row["scheduled_date"], time(18, 0), tzinfo=timezone.utc)
    end_at = _rget(row, "end_at") or (start_at + timedelta(minutes=int(row["duration_minutes"] or 30)))
    title = _rget(row, "title") or row["topic_title"] or "Study task"
    topic_stats = _json_value(_rget(row, "topic_stats"), None)
    scope_items = _json_value(_rget(row, "scope_items"), [])
    if not isinstance(topic_stats, dict):
        topic_stats = None
    if not isinstance(scope_items, list):
        scope_items = []
    scope_items = _task_scope_items_with_display_numbers(scope_items, topic_stats)
    return {
        "id": row["id"],
        "courseId": row["subject_id"],
        "subjectId": row["subject_id"],
        "courseName": _rget(row, "subject_name"),
        "subjectName": _rget(row, "subject_name"),
        "topicId": row["topic_id"],
        "subtopicId": _rget(row, "subtopic_id") or row["topic_id"],
        "parentTopicId": _rget(row, "parent_topic_id"),
        "title": title,
        "topicTitle": row["topic_title"] or title,
        "type": str(row["type"] or "review").lower(),
        "startAt": _iso(start_at),
        "endAt": _iso(end_at),
        "durationMinutes": row["duration_minutes"],
        "status": row["status"],
        "priority": _rget(row, "priority") or "medium",
        "reason": row["reason"] or "",
        "lessonId": _rget(row, "lesson_id"),
        "lessonTitle": _rget(row, "lesson_title") or _rget(row, "mapped_lesson_title"),
        "learningState": _rget(row, "learning_state"),
        "isPartialTopic": bool(_rget(row, "is_partial_topic", False)),
        "scope": _rget(row, "scope") or "subtopic",
        "topicStats": topic_stats,
        "scopeItems": scope_items,
        "earliestAllowedAt": _iso(_rget(row, "earliest_allowed_at")),
        "scheduledDate": _iso(row["scheduled_date"]),
        "day": row["day"],
    }


def _task_scope_items_with_display_numbers(scope_items: list[Any], topic_stats: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not scope_items:
        return []
    chapter_number = _chapter_number_from_text(str((topic_stats or {}).get("title") or (topic_stats or {}).get("id") or ""))
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(scope_items, start=1):
        if not isinstance(item, dict):
            continue
        copy = dict(item)
        title = str(copy.get("title") or "").strip()
        if title and not re.match(r"^\d+(?:\.\d+)*[.)]?\s+", title):
            section_number = _section_number_from_topic_id(str(copy.get("id") or "")) or index
            if chapter_number:
                title = f"{chapter_number}.{section_number}. {title}"
            else:
                title = f"{section_number}. {title}"
            copy["title"] = title
        normalized.append(copy)
    return normalized


def _section_number_from_topic_id(topic_id: str) -> int | None:
    match = re.search(r"-section-(\d+)$", topic_id)
    return int(match.group(1)) if match else None


def _busy_event_from_row(row: asyncpg.Record) -> dict[str, Any]:
    return {
        "id": row["id"],
        "userId": row["user_id"],
        "title": row["title"],
        "type": "busy",
        "startAt": _iso(row["start_at"]),
        "endAt": _iso(row["end_at"]),
        "reason": row["reason"] or "",
        "recurrenceId": _rget(row, "recurrence_id"),
        "createdAt": _iso(_rget(row, "created_at")),
        "updatedAt": _iso(_rget(row, "updated_at")),
    }


async def _get_busy_event_row(pool: asyncpg.Pool, event_id: str, user_id: str) -> asyncpg.Record | None:
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM busy_events WHERE id=$1 AND user_id=$2", event_id, user_id)


def _require_non_empty_text(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    return text


def _require_datetime(value: Any, field: str) -> datetime:
    parsed = _parse_datetime(value)
    if not parsed:
        raise ValueError(f"{field} must be a valid datetime")
    return parsed


def _require_time_order(start_at: datetime, end_at: datetime) -> None:
    if end_at <= start_at:
        raise ValueError("endAt must be after startAt")


def _chunk_from_row(row: asyncpg.Record) -> dict[str, Any]:
    return {
        "id": row["id"],
        "chunkId": row["id"],
        "courseId": row["subject_id"],
        "documentId": row["source_id"],
        "sourceId": row["source_id"],
        "filename": row["filename"],
        "chunkIndex": row["chunk_index"],
        "text": row["text"],
        "normalizedText": row["normalized_text"],
        "quote": row["quote"],
        "page": row["page"],
        "pageStart": row["page_start"],
        "pageEnd": row["page_end"],
        "sectionPath": row["section_path"],
        "sectionTitle": row["section_title"],
        "chapterName": row["section_path"],
        "topicName": row["section_title"],
        "topicIds": list(row["topic_ids"] or []),
        "embeddingStatus": row["embedding_status"],
        "embedding": row["embedding"] if "embedding" in row else None,
    }


def _thread_from_row(row: asyncpg.Record) -> dict[str, Any]:
    return {"id": row["id"], "courseId": row["subject_id"], "title": row["title"], "origin": row["origin"], "createdAt": _iso(row["created_at"]), "updatedAt": _iso(row["updated_at"])}


def _message_from_row(row: asyncpg.Record) -> dict[str, Any]:
    return {"id": row["id"], "threadId": row["thread_id"], "role": row["role"], "content": row["content"], "sourceRefs": _json_value(row["source_refs"], []), "actions": _json_value(row["actions"], []), "createdAt": _iso(row["created_at"])}


def _quiz_from_row(row: asyncpg.Record) -> dict[str, Any]:
    return {"id": row["id"], "courseId": row["subject_id"], "topicId": row["topic_id"], "title": row["title"], "difficulty": row["difficulty"], "instructions": row["instructions"], "selectedSourceIds": list(row["selected_source_ids"] or []), "questions": _json_value(row["questions"], []), "createdAt": _iso(row["created_at"])}


def _quiz_result_from_row(row: asyncpg.Record) -> dict[str, Any]:
    return {"id": row["id"], "quizId": row["quiz_id"], "courseId": row["subject_id"], "score": row["score"], "total": row["total"], "accuracyPercent": row["accuracy_percent"], "averageSecondsPerQuestion": row["average_seconds_per_question"], "mistakes": _json_value(row["mistakes"], []), "createdAt": _iso(row["created_at"])}


def _flashcard_from_row(row: asyncpg.Record) -> dict[str, Any]:
    return {"id": row["id"], "courseId": row["subject_id"], "topicId": row["topic_id"], "front": row["front"], "back": row["back"], "explanation": row["explanation"], "sourceRef": _json_value(row["source_ref"], None), "dueAt": _iso(row["due_at"]), "lastRating": row["last_rating"], "createdAt": _iso(row["created_at"])}


def _flashcard_session_from_row(row: asyncpg.Record) -> dict[str, Any]:
    return {"id": row["id"], "courseId": row["subject_id"], "flashcardIds": list(row["flashcard_ids"] or []), "ratings": _json_value(row["ratings"], {}), "status": row["status"], "createdAt": _iso(row["created_at"]), "updatedAt": _iso(row["updated_at"])}


def _subject_mode_to_course(mode: str) -> str:
    return "exam_sprint" if mode == "exam_sprint" else "continuous"


def _rget(row: asyncpg.Record, key: str, default: Any = None) -> Any:
    try:
        return row[key]
    except (KeyError, IndexError):
        return default


def _course_mode_to_subject(mode: str) -> str:
    return "exam_sprint" if mode in {"exam", "exam_sprint"} else "semester"


def _normalize_availability(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    mapping = {
        "T2": "Mon",
        "T3": "Tue",
        "T4": "Wed",
        "T5": "Thu",
        "T6": "Fri",
        "T7": "Sat",
        "CN": "Sun",
        "Mon": "Mon",
        "Tue": "Tue",
        "Wed": "Wed",
        "Thu": "Thu",
        "Fri": "Fri",
        "Sat": "Sat",
        "Sun": "Sun",
    }
    days: list[str] = []
    for item in value:
        day = mapping.get(str(item).strip())
        if day and day not in days:
            days.append(day)
    return days


DAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
DAY_INDEX = {day: index for index, day in enumerate(DAY_ORDER)}
DAY_ALIASES = {
    "T2": "Mon",
    "T3": "Tue",
    "T4": "Wed",
    "T5": "Thu",
    "T6": "Fri",
    "T7": "Sat",
    "CN": "Sun",
    "MON": "Mon",
    "TUE": "Tue",
    "WED": "Wed",
    "THU": "Thu",
    "FRI": "Fri",
    "SAT": "Sat",
    "SUN": "Sun",
}

def _availability_window_days(windows: list[dict[str, str]]) -> list[str]:
    days: list[str] = []
    for window in windows:
        day = window.get("day")
        if day and day not in days:
            days.append(day)
    return days

def _normalize_availability_windows(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise ValueError("availabilityWindows must include at least one time window")

    by_day: dict[str, list[tuple[int, int]]] = {day: [] for day in DAY_ORDER}
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("Each availability window must be an object")
        day = _normalize_window_day(item.get("day"))
        start = _parse_window_hhmm(item.get("start"), "start")
        end = _parse_window_hhmm(item.get("end"), "end")
        if end <= start:
            raise ValueError("availabilityWindows end must be after start")
        by_day[day].append((start, end))

    normalized: list[dict[str, str]] = []
    for day in DAY_ORDER:
        previous_end: int | None = None
        for start, end in sorted(by_day[day]):
            if previous_end is not None and start < previous_end:
                raise ValueError(f"availabilityWindows overlap on {day}")
            previous_end = end
            normalized.append({"day": day, "start": _format_window_hhmm(start), "end": _format_window_hhmm(end)})
    return normalized

def _normalize_window_day(value: Any) -> str:
    key = str(value or "").strip()
    if key in DAY_ORDER:
        return key
    day = DAY_ALIASES.get(key.upper())
    if not day:
        raise ValueError("availabilityWindows day must be a weekday")
    return day

def _parse_window_hhmm(value: Any, field: str) -> int:
    text = str(value or "").strip()
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", text)
    if not match:
        raise ValueError(f"availabilityWindows {field} must use HH:mm")
    hour = int(match.group(1))
    minute = int(match.group(2))
    if hour > 23 or minute > 59:
        raise ValueError(f"availabilityWindows {field} must use HH:mm")
    return hour * 60 + minute

def _format_window_hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"

def _file_type(filename: str) -> str:
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else "txt"
    return suffix if suffix in {"pdf", "docx", "pptx", "txt", "web"} else "txt"


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return date.fromisoformat(str(value)[:10])


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _parse_hhmm(value: str) -> tuple[int, int]:
    match = re.match(r"^(\d{1,2})(?::(\d{2}))?", value)
    if not match:
        return 18, 0
    return min(22, max(7, int(match.group(1)))), int(match.group(2) or 0)


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _date_from_iso(value: str | None) -> date | None:
    if not value:
        return None
    return _parse_datetime(value).date()


def _json_value(value: Any, default: Any) -> Any:
    if value is None:
        return default
    _max_depth = 10  # guard against pathological infinite-loop strings
    while isinstance(value, str) and _max_depth > 0:
        _max_depth -= 1
        try:
            decoded = json.loads(value)
            if decoded == value:  # stable fixed-point — a plain string
                break
            value = decoded
        except Exception:
            break
    if isinstance(default, dict) and isinstance(value, list):
        found = {}
        for item in value:
            if isinstance(item, dict) and ("lessons" in item or "normalizedLessons" in item or "progress" in item):
                found = item
                break
        if not found and value:
            for item in value:
                if isinstance(item, dict):
                    found = item
                    break
        value = found if found else default
    return value


def _answers_by_question_id(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, list):
        return {}
    normalized: dict[str, Any] = {}
    for item in value:
        if not isinstance(item, dict):
            continue
        question_id = item.get("questionId") or item.get("id")
        if not question_id:
            continue
        normalized[str(question_id)] = item.get("selectedAnswer") or item.get("selectedOption") or item.get("answer")
    return normalized


def _general_answer(message: str) -> str:
    normalized = normalize_for_search(message)
    if "entropy" in normalized:
        return "Entropy is a measure of how spread out energy is in a system; in simple terms, higher entropy means more possible arrangements and less usable concentrated energy."
    if "derivative" in normalized:
        return "A derivative tells you how fast something changes at a specific point, like the slope of a curve at that exact moment."
    return f"Here is a concise study explanation for your question: {message}" if message else "I'm here to help with your studies."
