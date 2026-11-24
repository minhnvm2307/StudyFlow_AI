from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from app.core.document.extractor import extract_text_from_file_path
from app.core.rag.embedding import get_embedding


USER_ID = "user-evaluation-test"
SUBJECT_ID = "subject-tthcm-evaluation"
OTHER_SUBJECT_ID = "subject-other-dummy"

BACKEND_ROOT = Path(__file__).resolve().parents[2]
TTHCM_ROOT = BACKEND_ROOT / "data" / "init" / "TTHCM"
MATERIAL_FILENAME = "TÀI LIỆU HỌC TẬP HP TƯ TƯỞNG HỒ CHÍ MINH.docx"
SYLLABUS_FILENAME = "Syllabus.docx"


@dataclass(frozen=True)
class RagSeedContext:
    user_id: str = USER_ID
    subject_id: str = SUBJECT_ID
    other_subject_id: str = OTHER_SUBJECT_ID


def _normalize_whitespace(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _read_tthcm_doc(filename: str) -> str:
    path = TTHCM_ROOT / filename
    return _normalize_whitespace(extract_text_from_file_path(str(path)))


def _parse_syllabus_chapters(syllabus_text: str) -> list[dict[str, object]]:
    chapters_by_num: dict[int, dict[str, object]] = {}
    current_week: int | None = None
    current_chapter_num: int | None = None

    for raw_line in syllabus_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.isdigit():
            current_week = int(line)
            continue

        chapter_match = re.match(r"^Chương\s+(\d+):\s*(.+)$", line, re.IGNORECASE)
        if chapter_match:
            current_chapter_num = int(chapter_match.group(1))
            chapter = chapters_by_num.setdefault(
                current_chapter_num,
                {
                    "number": current_chapter_num,
                    "title": f"Chương {current_chapter_num}: {chapter_match.group(2).strip()}",
                    "lessons": [],
                },
            )
            chapter["title"] = f"Chương {current_chapter_num}: {chapter_match.group(2).strip()}"
            continue

        lesson_match = re.match(r"^(\d+\.\d+)\.?\s+(.+)$", line)
        if lesson_match and current_chapter_num is not None:
            chapter = chapters_by_num[current_chapter_num]
            chapter["lessons"].append(
                {
                    "title": f"{lesson_match.group(1)} {lesson_match.group(2).strip()}",
                    "weekNumber": current_week or current_chapter_num,
                }
            )

    return [chapters_by_num[key] for key in sorted(chapters_by_num)]


def _split_material_by_chapter(material_text: str, chapters: list[dict[str, object]]) -> list[dict[str, str]]:
    chapter_titles = {
        int(chapter["number"]): str(chapter["title"])
        for chapter in chapters
    }
    pattern = re.compile(
        r"(^Chương\s+(\d+)\s*$)(.*?)(?=^Chương\s+\d+\s*$|\Z)",
        re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    sections: list[dict[str, str]] = []
    for match in pattern.finditer(material_text):
        chapter_num = int(match.group(2))
        body = _normalize_whitespace(match.group(3))
        if not body:
            continue
        sections.append(
            {
                "number": str(chapter_num),
                "title": chapter_titles.get(chapter_num, f"Chương {chapter_num}"),
                "text": body,
            }
        )
    return sections


def _chunk_chapter_text(chapter_text: str, *, chunk_size: int = 1600) -> list[str]:
    paragraphs = [paragraph.strip() for paragraph in chapter_text.split("\n") if paragraph.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for paragraph in paragraphs:
        paragraph_len = len(paragraph)
        if current and current_len + paragraph_len + 2 > chunk_size:
            chunks.append("\n\n".join(current))
            current = [paragraph]
            current_len = paragraph_len
            continue
        current.append(paragraph)
        current_len += paragraph_len + (2 if current_len else 0)

    if current:
        chunks.append("\n\n".join(current))
    return chunks


def load_tthcm_seed_payload() -> dict[str, object]:
    syllabus_text = _read_tthcm_doc(SYLLABUS_FILENAME)
    material_text = _read_tthcm_doc(MATERIAL_FILENAME)
    chapters = _parse_syllabus_chapters(syllabus_text)
    sections = _split_material_by_chapter(material_text, chapters)

    chunks: list[dict[str, str | int]] = []
    for section in sections:
        chapter_num = int(section["number"])
        topic_id = f"topic-tthcm-{chapter_num}"
        for chunk_index, chunk_text in enumerate(_chunk_chapter_text(section["text"]), start=1):
            chunks.append(
                {
                    "topic_id": topic_id,
                    "title": str(section["title"]),
                    "chunk_index": chunk_index,
                    "text": chunk_text,
                }
            )

    return {
        "subject_name": "Tư tưởng Hồ Chí Minh",
        "syllabus_text": syllabus_text,
        "material_text": material_text,
        "chapters": chapters,
        "chunks": chunks,
    }


async def _cleanup_seed_records(conn, ctx: RagSeedContext) -> None:
    subject_ids = [ctx.subject_id, ctx.other_subject_id]
    syllabus_ids = [f"syllabus-{ctx.subject_id}"]
    await conn.execute("DELETE FROM study_tasks WHERE user_id = $1 OR subject_id = ANY($2::text[])", ctx.user_id, subject_ids)
    await conn.execute("DELETE FROM topics WHERE user_id = $1 OR subject_id = ANY($2::text[])", ctx.user_id, subject_ids)
    await conn.execute(
        "DELETE FROM syllabus_lessons WHERE subject_id = ANY($1::text[]) OR syllabus_id = ANY($2::text[])",
        subject_ids,
        syllabus_ids,
    )
    await conn.execute("DELETE FROM course_syllabi WHERE user_id = $1 OR subject_id = ANY($2::text[])", ctx.user_id, subject_ids)
    await conn.execute("DELETE FROM document_chunks WHERE user_id = $1 OR subject_id = ANY($2::text[])", ctx.user_id, subject_ids)
    await conn.execute("DELETE FROM course_sources WHERE user_id = $1 OR subject_id = ANY($2::text[])", ctx.user_id, subject_ids)
    await conn.execute("DELETE FROM subjects WHERE user_id = $1 OR id = ANY($2::text[])", ctx.user_id, subject_ids)
    await conn.execute("DELETE FROM users WHERE id = $1", ctx.user_id)


async def seed_rag_eval_data(pool) -> RagSeedContext:
    ctx = RagSeedContext()
    payload = load_tthcm_seed_payload()
    chapters = payload["chapters"]
    material_chunks = payload["chunks"]

    async with pool.acquire() as conn:
        await _cleanup_seed_records(conn, ctx)
        await conn.execute(
            """
            INSERT INTO users (id, username, email, password_hash, onboarding_step)
            VALUES ($1, $2, $3, 'dummy', 2)
            ON CONFLICT (id) DO UPDATE
            SET username = EXCLUDED.username,
                email = EXCLUDED.email,
                password_hash = EXCLUDED.password_hash,
                onboarding_step = EXCLUDED.onboarding_step
            """,
            ctx.user_id,
            "eval_user",
            "eval@studyflow.com",
        )
        await conn.execute(
            """
            INSERT INTO subjects (id, user_id, name, mode, exam_date)
            VALUES ($1, $2, $3, 'semester', $4)
            ON CONFLICT (id) DO UPDATE
            SET user_id = EXCLUDED.user_id,
                name = EXCLUDED.name,
                mode = EXCLUDED.mode,
                exam_date = EXCLUDED.exam_date
            """,
            ctx.subject_id,
            ctx.user_id,
            payload["subject_name"],
            date.today() + timedelta(days=20),
        )
        await conn.execute(
            """
            INSERT INTO subjects (id, user_id, name, mode, exam_date)
            VALUES ($1, $2, $3, 'semester', $4)
            ON CONFLICT (id) DO UPDATE
            SET user_id = EXCLUDED.user_id,
                name = EXCLUDED.name,
                mode = EXCLUDED.mode,
                exam_date = EXCLUDED.exam_date
            """,
            ctx.other_subject_id,
            ctx.user_id,
            "Môn học Nhiễu",
            date.today() + timedelta(days=20),
        )

        await conn.execute(
            """
            INSERT INTO course_sources (id, subject_id, user_id, filename, status)
            VALUES ($1, $2, $3, $4, 'ready')
            ON CONFLICT (id) DO UPDATE
            SET subject_id = EXCLUDED.subject_id,
                user_id = EXCLUDED.user_id,
                filename = EXCLUDED.filename,
                status = EXCLUDED.status
            """,
            f"source-{ctx.subject_id}",
            ctx.subject_id,
            ctx.user_id,
            MATERIAL_FILENAME,
        )
        await conn.execute(
            """
            INSERT INTO course_sources (id, subject_id, user_id, filename, status)
            VALUES ($1, $2, $3, $4, 'ready')
            ON CONFLICT (id) DO UPDATE
            SET subject_id = EXCLUDED.subject_id,
                user_id = EXCLUDED.user_id,
                filename = EXCLUDED.filename,
                status = EXCLUDED.status
            """,
            f"syllabus-{ctx.subject_id}",
            ctx.subject_id,
            ctx.user_id,
            SYLLABUS_FILENAME,
        )
        await conn.execute(
            """
            INSERT INTO course_sources (id, subject_id, user_id, filename, status)
            VALUES ($1, $2, $3, $4, 'ready')
            ON CONFLICT (id) DO UPDATE
            SET subject_id = EXCLUDED.subject_id,
                user_id = EXCLUDED.user_id,
                filename = EXCLUDED.filename,
                status = EXCLUDED.status
            """,
            f"source-{ctx.other_subject_id}",
            ctx.other_subject_id,
            ctx.user_id,
            "other.txt",
        )

        for global_index, chunk in enumerate(material_chunks, start=1):
            chunk_id = f"chunk-{ctx.subject_id}-{global_index}"
            await conn.execute(
                """
                INSERT INTO document_chunks (id, subject_id, source_id, user_id, filename, chunk_index, text, embedding, topic_ids)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8::real[], $9)
                ON CONFLICT (id) DO UPDATE
                SET subject_id = EXCLUDED.subject_id,
                    source_id = EXCLUDED.source_id,
                    user_id = EXCLUDED.user_id,
                    filename = EXCLUDED.filename,
                    chunk_index = EXCLUDED.chunk_index,
                    text = EXCLUDED.text,
                    embedding = EXCLUDED.embedding,
                    topic_ids = EXCLUDED.topic_ids
                """,
                chunk_id,
                ctx.subject_id,
                f"source-{ctx.subject_id}",
                ctx.user_id,
                MATERIAL_FILENAME,
                int(chunk["chunk_index"]),
                str(chunk["text"]),
                get_embedding(str(chunk["text"])),
                [str(chunk["topic_id"])],
            )

        noise_text = "Khái niệm quản trị học là nghiên cứu cách tổ chức, điều hành và kiểm soát hoạt động của một doanh nghiệp."
        await conn.execute(
            """
            INSERT INTO document_chunks (id, subject_id, source_id, user_id, filename, chunk_index, text, embedding, topic_ids)
            VALUES ($1, $2, $3, $4, $5, 1, $6, $7::real[], $8)
            ON CONFLICT (id) DO UPDATE
            SET subject_id = EXCLUDED.subject_id,
                source_id = EXCLUDED.source_id,
                user_id = EXCLUDED.user_id,
                filename = EXCLUDED.filename,
                chunk_index = EXCLUDED.chunk_index,
                text = EXCLUDED.text,
                embedding = EXCLUDED.embedding,
                topic_ids = EXCLUDED.topic_ids
            """,
            f"chunk-{ctx.other_subject_id}-1",
            ctx.other_subject_id,
            f"source-{ctx.other_subject_id}",
            ctx.user_id,
            "other.txt",
            noise_text,
            get_embedding(noise_text),
            ["topic-noise-1"],
        )

        parsed_syllabus = {
            "chapters": [
                {
                    "title": str(chapter["title"]),
                    "lessons": list(chapter["lessons"]),
                }
                for chapter in chapters
            ]
        }
        await conn.execute(
            """
            INSERT INTO course_syllabi (id, subject_id, user_id, status, parsed_json)
            VALUES ($1, $2, $3, 'ready', $4)
            ON CONFLICT (id) DO UPDATE
            SET subject_id = EXCLUDED.subject_id,
                user_id = EXCLUDED.user_id,
                status = EXCLUDED.status,
                parsed_json = EXCLUDED.parsed_json
            """,
            f"syllabus-{ctx.subject_id}",
            ctx.subject_id,
            ctx.user_id,
            json.dumps(parsed_syllabus, ensure_ascii=False),
        )

        for chapter in chapters:
            chapter_num = int(chapter["number"])
            lesson_title = str(chapter["lessons"][0]["title"]) if chapter["lessons"] else str(chapter["title"])
            week_number = int(chapter["lessons"][0]["weekNumber"]) if chapter["lessons"] else chapter_num
            starts_on = date.today() - timedelta(days=2) if chapter_num == 1 else date.today() + timedelta(days=(chapter_num - 1) * 7)
            ends_on = starts_on + timedelta(days=6)
            await conn.execute(
                """
                INSERT INTO syllabus_lessons (
                    id, syllabus_id, subject_id, week_number, lesson_number, title,
                    starts_on, ends_on, status, order_idx
                ) VALUES ($1, $2, $3, $4, 1, $5, $6, $7, $8, $9)
                ON CONFLICT (id) DO UPDATE
                SET syllabus_id = EXCLUDED.syllabus_id,
                    subject_id = EXCLUDED.subject_id,
                    week_number = EXCLUDED.week_number,
                    lesson_number = EXCLUDED.lesson_number,
                    title = EXCLUDED.title,
                    starts_on = EXCLUDED.starts_on,
                    ends_on = EXCLUDED.ends_on,
                    status = EXCLUDED.status,
                    order_idx = EXCLUDED.order_idx
                """,
                f"lesson-tthcm-{chapter_num}",
                f"syllabus-{ctx.subject_id}",
                ctx.subject_id,
                week_number,
                lesson_title,
                starts_on,
                ends_on,
                "current" if chapter_num == 1 else "upcoming",
                chapter_num,
            )

        for order_idx, chapter in enumerate(chapters, start=1):
            chapter_num = int(chapter["number"])
            topic_id = f"topic-tthcm-{chapter_num}"
            topic_content = next(
                (
                    str(item["text"])
                    for item in material_chunks
                    if str(item["topic_id"]) == topic_id
                ),
                str(chapter["title"]),
            )
            await conn.execute(
                """
                INSERT INTO topics (id, subject_id, user_id, title, content_chunk, order_idx, lesson_id, practice_allowed)
                VALUES ($1, $2, $3, $4, $5, $6, $7, true)
                ON CONFLICT (id) DO UPDATE
                SET subject_id = EXCLUDED.subject_id,
                    user_id = EXCLUDED.user_id,
                    title = EXCLUDED.title,
                    content_chunk = EXCLUDED.content_chunk,
                    order_idx = EXCLUDED.order_idx,
                    lesson_id = EXCLUDED.lesson_id,
                    practice_allowed = EXCLUDED.practice_allowed
                """,
                topic_id,
                ctx.subject_id,
                ctx.user_id,
                str(chapter["title"]),
                topic_content[:3000],
                order_idx,
                f"lesson-tthcm-{chapter_num}",
            )

        await conn.execute(
            """
            INSERT INTO study_tasks (
                id, subject_id, topic_id, user_id, topic_title, type,
                duration_minutes, scheduled_date, status, day, lesson_id,
                start_at, end_at
            ) VALUES ($1, $2, $3, $4, $5, 'REVIEW', 45, $6, 'ready', $7, $8, $9, $10)
            ON CONFLICT (id) DO UPDATE
            SET subject_id = EXCLUDED.subject_id,
                topic_id = EXCLUDED.topic_id,
                user_id = EXCLUDED.user_id,
                topic_title = EXCLUDED.topic_title,
                type = EXCLUDED.type,
                duration_minutes = EXCLUDED.duration_minutes,
                scheduled_date = EXCLUDED.scheduled_date,
                status = EXCLUDED.status,
                day = EXCLUDED.day,
                lesson_id = EXCLUDED.lesson_id,
                start_at = EXCLUDED.start_at,
                end_at = EXCLUDED.end_at
            """,
            "task-tthcm-1",
            ctx.subject_id,
            "topic-tthcm-1",
            ctx.user_id,
            str(chapters[0]["title"]),
            date.today(),
            date.today().strftime("%a"),
            "lesson-tthcm-1",
            datetime.combine(date.today(), datetime.min.time()) + timedelta(hours=18),
            datetime.combine(date.today(), datetime.min.time()) + timedelta(hours=18, minutes=45),
        )

    return ctx


async def cleanup_rag_eval_data(pool, user_id: str = USER_ID) -> None:
    ctx = RagSeedContext(user_id=user_id)
    async with pool.acquire() as conn:
        await _cleanup_seed_records(conn, ctx)
