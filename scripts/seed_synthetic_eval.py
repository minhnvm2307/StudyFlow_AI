from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import random
import secrets
import sys
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from statistics import mean
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import asyncpg

from app.db import repository
from app.db.pg_pool import close_pool, get_pool, init_pool
from app.schemas import FsrsReviewLog, Topic
from app.services import course_api_service as course_svc
from app.services.mastery_service import BatchQuestionOutcome, apply_objective_batch
from app.services.review_service import _batch_rating, _due_date_from_card
from app.services.unified_scheduler import build_unified_schedule
from app.core.rag.text import normalize_for_search
from app.core.scheduler import FSRSScheduler, get_scheduler


DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "eval"
DEFAULT_PASSWORD = "synthetic-2026"


@dataclass(frozen=True)
class TopicTemplate:
    title: str
    summary: str
    difficulty: float
    lesson_title: str
    keywords: tuple[str, ...]


@dataclass(frozen=True)
class CourseTemplate:
    name: str
    mode: str
    priority: str
    exam_offset_days: int
    featured: bool
    availability_windows: tuple[dict[str, str], ...]
    topics: tuple[TopicTemplate, ...]


@dataclass(frozen=True)
class PersonaTemplate:
    key: str
    label: str
    daily_goal_minutes: int
    study_days: tuple[str, ...]
    mascot_tone: str
    performance_bias: float
    missed_task_bias: float
    goal_mode: str
    xp_seed: int
    streak_seed: int
    courses: tuple[CourseTemplate, ...]


@dataclass
class SeededUser:
    user_id: str
    username: str
    email: str
    password: str
    persona_key: str
    persona_label: str
    course_ids: list[str]


LINEAR_ALGEBRA = CourseTemplate(
    name="Linear Algebra",
    mode="continuous",
    priority="high",
    exam_offset_days=19,
    featured=True,
    availability_windows=(
        {"day": "Mon", "start": "19:00", "end": "21:00"},
        {"day": "Wed", "start": "19:00", "end": "21:00"},
        {"day": "Sat", "start": "09:00", "end": "11:00"},
    ),
    topics=(
        TopicTemplate("Vector spaces", "Vector spaces describe sets closed under addition and scalar multiplication.", 0.28, "Vector spaces", ("basis", "subspace", "linear combination")),
        TopicTemplate("Linear transformations", "Linear transformations preserve vector addition and scalar multiplication.", 0.40, "Linear transformations", ("kernel", "image", "matrix representation")),
        TopicTemplate("Eigenvalues and eigenvectors", "An eigenvector keeps its direction after multiplication by the matrix, scaled by the eigenvalue.", 0.62, "Eigenvalues and eigenvectors", ("characteristic polynomial", "eigenvector", "eigenvalue")),
        TopicTemplate("Diagonalization", "A matrix is diagonalizable when it has enough linearly independent eigenvectors to form a basis.", 0.70, "Diagonalization", ("similarity transform", "independent eigenvectors", "power of matrix")),
    ),
)

PROBABILITY = CourseTemplate(
    name="Probability and Statistics",
    mode="continuous",
    priority="medium",
    exam_offset_days=26,
    featured=False,
    availability_windows=(
        {"day": "Tue", "start": "18:30", "end": "20:30"},
        {"day": "Thu", "start": "19:00", "end": "21:00"},
        {"day": "Sun", "start": "09:00", "end": "10:30"},
    ),
    topics=(
        TopicTemplate("Random variables", "A random variable maps outcomes to numerical values.", 0.30, "Random variables", ("distribution", "support", "variance")),
        TopicTemplate("Expectation and variance", "Expectation is the weighted average and variance measures spread around the mean.", 0.38, "Expectation and variance", ("linearity", "variance", "standard deviation")),
        TopicTemplate("Conditional probability", "Conditional probability updates likelihoods given observed evidence.", 0.58, "Conditional probability", ("Bayes rule", "dependence", "posterior")),
        TopicTemplate("Hypothesis testing", "Hypothesis testing compares data evidence against a null hypothesis using a decision threshold.", 0.72, "Hypothesis testing", ("p-value", "type I error", "confidence interval")),
    ),
)

CALCULUS = CourseTemplate(
    name="Calculus II",
    mode="exam_sprint",
    priority="high",
    exam_offset_days=11,
    featured=True,
    availability_windows=(
        {"day": "Mon", "start": "20:00", "end": "21:30"},
        {"day": "Thu", "start": "20:00", "end": "21:30"},
        {"day": "Sun", "start": "14:00", "end": "17:00"},
    ),
    topics=(
        TopicTemplate("Double integrals", "Double integrals accumulate values over a two-dimensional region.", 0.34, "Double integrals", ("iterated integral", "bounds", "region")),
        TopicTemplate("Change of variables", "Change of variables rewrites an integral using a new coordinate system and a Jacobian.", 0.56, "Change of variables", ("Jacobian", "polar coordinates", "substitution")),
        TopicTemplate("Fourier series", "Fourier series represent periodic functions using sines and cosines.", 0.68, "Fourier series", ("orthogonality", "coefficients", "periodic function")),
        TopicTemplate("Differential equations", "Differential equations connect a function with its derivatives to describe dynamic systems.", 0.76, "Differential equations", ("homogeneous", "particular solution", "initial condition")),
    ),
)

PHYSICS = CourseTemplate(
    name="Physics II",
    mode="exam_sprint",
    priority="medium",
    exam_offset_days=15,
    featured=False,
    availability_windows=(
        {"day": "Tue", "start": "19:30", "end": "21:00"},
        {"day": "Fri", "start": "19:30", "end": "21:30"},
        {"day": "Sat", "start": "15:00", "end": "17:00"},
    ),
    topics=(
        TopicTemplate("Electric field", "Electric field describes force per unit charge caused by electric sources.", 0.33, "Electric field", ("Coulomb law", "field lines", "superposition")),
        TopicTemplate("Magnetic force", "Magnetic force bends moving charges according to the Lorentz force.", 0.49, "Magnetic force", ("Lorentz force", "right hand rule", "circular motion")),
        TopicTemplate("Electromagnetic induction", "Changing magnetic flux induces electromotive force.", 0.66, "Electromagnetic induction", ("Faraday law", "flux", "Lenz law")),
        TopicTemplate("AC circuits", "Alternating current circuits combine resistance, capacitance, and inductance over time-varying signals.", 0.75, "AC circuits", ("impedance", "phase", "resonance")),
    ),
)

OPERATING_SYSTEMS = CourseTemplate(
    name="Operating Systems",
    mode="continuous",
    priority="high",
    exam_offset_days=31,
    featured=True,
    availability_windows=(
        {"day": "Mon", "start": "18:30", "end": "20:30"},
        {"day": "Wed", "start": "20:00", "end": "21:30"},
        {"day": "Sat", "start": "10:00", "end": "12:00"},
    ),
    topics=(
        TopicTemplate("Processes and threads", "Processes isolate resources while threads share process memory for concurrent execution.", 0.35, "Processes and threads", ("context switch", "concurrency", "thread states")),
        TopicTemplate("CPU scheduling", "CPU scheduling decides which runnable process gets processor time next.", 0.52, "CPU scheduling", ("round robin", "waiting time", "starvation")),
        TopicTemplate("Memory management", "Memory management maps logical addresses to physical memory and storage.", 0.67, "Memory management", ("paging", "segmentation", "page fault")),
        TopicTemplate("Deadlocks", "Deadlocks happen when processes wait on each other with no safe progress path.", 0.79, "Deadlocks", ("circular wait", "resource allocation graph", "avoidance")),
    ),
)

DATABASES = CourseTemplate(
    name="Database Systems",
    mode="continuous",
    priority="medium",
    exam_offset_days=36,
    featured=False,
    availability_windows=(
        {"day": "Tue", "start": "20:00", "end": "21:00"},
        {"day": "Thu", "start": "19:00", "end": "21:00"},
        {"day": "Sun", "start": "09:30", "end": "11:30"},
    ),
    topics=(
        TopicTemplate("ER modeling", "ER modeling captures entities, attributes, and relationships before implementation.", 0.29, "ER modeling", ("entity", "relationship", "cardinality")),
        TopicTemplate("Normalization", "Normalization reduces redundancy by decomposing relations into higher normal forms.", 0.50, "Normalization", ("functional dependency", "3NF", "BCNF")),
        TopicTemplate("Indexes and query plans", "Indexes trade storage for faster lookup and influence the query planner.", 0.63, "Indexes and query plans", ("B-tree", "sequential scan", "cost estimate")),
        TopicTemplate("Transactions and isolation", "Transactions group operations atomically while isolation controls concurrent visibility.", 0.77, "Transactions and isolation", ("ACID", "serializability", "deadlock")),
    ),
)

PERSONAS = (
    PersonaTemplate(
        key="steady",
        label="Steady Achiever",
        daily_goal_minutes=90,
        study_days=("Mon", "Tue", "Wed", "Thu", "Sat"),
        mascot_tone="encouraging",
        performance_bias=0.82,
        missed_task_bias=0.08,
        goal_mode="semester",
        xp_seed=640,
        streak_seed=11,
        courses=(LINEAR_ALGEBRA, PROBABILITY),
    ),
    PersonaTemplate(
        key="sprint",
        label="Last-Minute Sprinter",
        daily_goal_minutes=55,
        study_days=("Tue", "Thu", "Sat", "Sun"),
        mascot_tone="focused",
        performance_bias=0.61,
        missed_task_bias=0.24,
        goal_mode="exam_sprint",
        xp_seed=320,
        streak_seed=4,
        courses=(CALCULUS, PHYSICS),
    ),
    PersonaTemplate(
        key="overloaded",
        label="Overloaded Struggler",
        daily_goal_minutes=45,
        study_days=("Mon", "Wed", "Fri"),
        mascot_tone="gentle",
        performance_bias=0.47,
        missed_task_bias=0.46,
        goal_mode="semester",
        xp_seed=180,
        streak_seed=1,
        courses=(OPERATING_SYSTEMS, DATABASES),
    ),
)


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000).hex()
    return f"{salt}${digest}"


def slugify(value: str) -> str:
    return "-".join(part for part in "".join(ch.lower() if ch.isalnum() else "-" for ch in value).split("-") if part)


def choose_persona(index: int) -> PersonaTemplate:
    return PERSONAS[index % len(PERSONAS)]


def build_user_identity(prefix: str, persona: PersonaTemplate, index: int) -> tuple[str, str, str]:
    username = f"{prefix}-{persona.key}-{index + 1:02d}"
    email = f"{username}@synthetic.studyflow.local"
    user_id = f"user-{username}"
    return user_id, username, email


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def safe_int(value: float) -> int:
    return max(0, int(round(value)))


def utc_from_local_day(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour=hour, minute=minute), tzinfo=timezone.utc)


def topic_id_for(course_id: str, order_idx: int) -> str:
    return f"topic-{course_id}-syllabus-{order_idx + 1:02d}"


def lesson_payloads_for_course(course: CourseTemplate, today: date) -> tuple[list[dict[str, Any]], int, int]:
    lessons: list[dict[str, Any]] = []
    for index, topic in enumerate(course.topics):
        lesson_day = today + timedelta(days=(index - 2) * 7)
        lessons.append({
            "weekNumber": index + 1,
            "lessonNumber": 1,
            "title": topic.lesson_title,
            "description": f"Structured study session for {topic.title}.",
            "assignedReadings": [f"{course.name} chapter {index + 1}"],
            "startsOn": lesson_day.isoformat(),
            "endsOn": lesson_day.isoformat(),
        })
    return lessons, 3, 1


async def ensure_prerequisites(pool: asyncpg.Pool) -> None:
    await repository.ensure_busy_events_table(pool)
    await repository.ensure_topic_mastery_evidence_columns(pool)
    await repository.ensure_mastery_events_table(pool)


async def cleanup_synthetic_users(pool: asyncpg.Pool, prefix: str) -> int:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id FROM users WHERE username ILIKE $1 OR email ILIKE $2",
            f"{prefix}%",
            f"{prefix}%@synthetic.studyflow.local",
        )
        user_ids = [row["id"] for row in rows]
        if user_ids:
            await conn.execute("DELETE FROM users WHERE id = ANY($1::text[])", user_ids)
    return len(user_ids)


def build_rng(seed: int, *parts: str) -> random.Random:
    token = "|".join([str(seed), *parts])
    return random.Random(token)


async def create_synthetic_user(
    pool: asyncpg.Pool,
    *,
    prefix: str,
    persona: PersonaTemplate,
    index: int,
    password: str,
) -> SeededUser:
    user_id, username, email = build_user_identity(prefix, persona, index)
    await repository.create_user(pool, user_id, email, hash_password(password), username)
    await repository.update_profile(
        pool,
        user_id,
        onboarding_step=2,
        goal_mode=persona.goal_mode,
        daily_goal_minutes=persona.daily_goal_minutes,
        study_days=list(persona.study_days),
        mascot_tone=persona.mascot_tone,
        xp=persona.xp_seed,
        streak=persona.streak_seed,
        notifications={"schedule": True, "reviews": True, "deadline": True},
    )
    return SeededUser(
        user_id=user_id,
        username=username,
        email=email,
        password=password,
        persona_key=persona.key,
        persona_label=persona.label,
        course_ids=[],
    )


async def create_course_with_syllabus(
    pool: asyncpg.Pool,
    user: SeededUser,
    course_template: CourseTemplate,
    *,
    today: date,
    course_index: int,
) -> tuple[str, dict[str, Any]]:
    course = await course_svc.create_course(
        pool,
        {
            "name": course_template.name,
            "mode": course_template.mode,
            "priority": course_template.priority,
            "featured": course_template.featured,
            "examDate": (today + timedelta(days=course_template.exam_offset_days)).isoformat(),
            "dailyGoalMinutes": 45 if course_template.mode == "exam_sprint" else 30,
            "availabilityWindows": list(course_template.availability_windows),
            "autoGeneratePlan": False,
        },
        user.user_id,
    )
    lessons, current_week, current_lesson_number = lesson_payloads_for_course(course_template, today)
    syllabus = await course_svc.create_syllabus(
        pool,
        course["id"],
        {
            "mode": "manual",
            "currentWeek": current_week,
            "currentLessonNumber": current_lesson_number,
            "joinPosition": "mid_semester",
            "lessons": lessons,
            "chapters": [
                {"title": topic.title, "topics": [topic.title]}
                for topic in course_template.topics
            ],
            "filename": f"{slugify(course_template.name)}-syllabus-{course_index + 1}.txt",
        },
        user.user_id,
    )
    return course["id"], syllabus


def make_topic_seed(
    *,
    course_id: str,
    user_id: str,
    topic_template: TopicTemplate,
    order_idx: int,
    lesson_row: dict[str, Any],
    rng: random.Random,
    persona: PersonaTemplate,
    course_mode: str,
) -> Topic:
    initial_mastery = clamp(0.14 + persona.performance_bias * 0.42 - topic_template.difficulty * 0.18 + rng.uniform(-0.05, 0.05), 0.08, 0.72)
    lesson_status = str(lesson_row.get("status") or "future")
    practice_allowed = lesson_status != "future" or course_mode == "exam_sprint"
    starts_on = lesson_row.get("startsOn")
    ends_on = lesson_row.get("endsOn")

    return Topic(
        id=topic_id_for(course_id, order_idx),
        subject_id=course_id,
        user_id=user_id,
        title=topic_template.title,
        description=topic_template.summary,
        section_number=order_idx + 1,
        content_chunk=topic_template.summary,
        order_idx=order_idx,
        cost_mins=max(10, min(30, 15 + round((1 - initial_mastery) * 15))),
        mastery=initial_mastery,
        p_l0=0.05,
        p_t=0.2,
        p_g=0.2,
        p_s=0.1,
        awaiting_diagnostic=practice_allowed,
        fsrs_card={},
        fsrs_stability=0.0,
        fsrs_difficulty=5.0 + topic_template.difficulty * 2.5,
        fsrs_last_review=None,
        fsrs_due_date=None,
        merged_from=[],
        is_learned=False,
        parent_topic_id=None,
        parent_topic_title=None,
        is_subtopic=False,
        lesson_id=lesson_row["id"],
        learning_state=lesson_status,
        practice_allowed=practice_allowed,
        lesson_starts_on=date.fromisoformat(starts_on) if isinstance(starts_on, str) else starts_on,
        lesson_ends_on=date.fromisoformat(ends_on) if isinstance(ends_on, str) else ends_on,
    )


async def save_seed_topics(
    pool: asyncpg.Pool,
    *,
    user: SeededUser,
    course_id: str,
    course_template: CourseTemplate,
    syllabus: dict[str, Any],
    persona: PersonaTemplate,
    seed: int,
) -> list[Topic]:
    lesson_by_title = {lesson["title"]: lesson for lesson in syllabus.get("lessons", [])}
    topics: list[Topic] = []
    for order_idx, topic_template in enumerate(course_template.topics):
        lesson_row = lesson_by_title[topic_template.lesson_title]
        rng = build_rng(seed, user.user_id, course_id, topic_template.title)
        topics.append(
            make_topic_seed(
                course_id=course_id,
                user_id=user.user_id,
                topic_template=topic_template,
                order_idx=order_idx,
                lesson_row=lesson_row,
                rng=rng,
                persona=persona,
                course_mode=course_template.mode,
            )
        )
    async with pool.acquire() as conn:
        lesson_ids = [lesson["id"] for lesson in syllabus.get("lessons", [])]
        async with conn.transaction():
            if lesson_ids:
                await conn.execute("DELETE FROM lesson_material_mappings WHERE lesson_id = ANY($1::text[])", lesson_ids)
            await conn.execute("DELETE FROM topics WHERE subject_id=$1 AND user_id=$2", course_id, user.user_id)
    await repository.save_topics(pool, topics)
    saved_topics: list[Topic] = []
    for topic in topics:
        row = await repository.get_topic(pool, topic.id)
        if row:
            saved_topics.append(row)
    return saved_topics


async def _document_chunk_has_embedding_column(conn: asyncpg.Connection) -> bool:
    row = await conn.fetchrow(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_name='document_chunks' AND column_name='embedding'
        """
    )
    return bool(row)


async def seed_sources_and_chunks(
    pool: asyncpg.Pool,
    *,
    user: SeededUser,
    course_id: str,
    course_template: CourseTemplate,
    topics: list[Topic],
    created_at: datetime,
) -> dict[str, Any]:
    source_id = f"source_{uuid.uuid4().hex[:10]}"
    filename = f"{slugify(course_template.name)}-synthetic-notes.txt"
    topic_by_title = {topic.title: topic for topic in topics}

    sections = []
    for topic_template in course_template.topics:
        sections.append(
            f"Topic: {topic_template.title}\n"
            f"{topic_template.summary}\n"
            f"Keywords: {', '.join(topic_template.keywords)}."
        )
    text_content = "\n\n".join(sections)

    chunks: list[dict[str, Any]] = []
    for index, topic_template in enumerate(course_template.topics):
        topic = topic_by_title[topic_template.title]
        chunk_text = (
            f"{topic_template.title} belongs to {course_template.name}. "
            f"{topic_template.summary} "
            f"Key reminders: {', '.join(topic_template.keywords)}."
        )
        chunks.append(
            {
                "id": f"chunk_{uuid.uuid4().hex[:10]}",
                "topic": topic,
                "text": chunk_text,
                "quote": topic_template.summary[:220],
                "section_title": topic_template.title,
                "topic_ids": [topic.id],
                "chunk_index": index + 1,
                "content_hash": hashlib.sha1(chunk_text.encode("utf-8")).hexdigest(),
                "token_count": len(chunk_text.split()),
            }
        )

    async with pool.acquire() as conn:
        has_embedding = await _document_chunk_has_embedding_column(conn)
        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO course_sources (
                    id, subject_id, user_id, filename, original_name, file_type, mime_type,
                    status, selected, topic_count, text_content, parsed_at, uploaded_at, created_at
                )
                VALUES ($1,$2,$3,$4,$5,'txt','text/plain','ready',true,$6,$7,$8,$8,$8)
                """,
                source_id,
                course_id,
                user.user_id,
                filename,
                filename,
                len(chunks),
                text_content,
                created_at,
            )

            for chunk in chunks:
                if has_embedding:
                    await conn.execute(
                        """
                        INSERT INTO document_chunks (
                            id, subject_id, source_id, user_id, filename, chunk_index, text,
                            normalized_text, quote, page, page_start, page_end, section_path,
                            section_title, topic_ids, content_hash, token_count, embedding_status,
                            metadata, created_at, embedding
                        )
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$10,$10,$11,$12,$13,$14,$15,'disabled',$16,$17,NULL)
                        """,
                        chunk["id"],
                        course_id,
                        source_id,
                        user.user_id,
                        filename,
                        chunk["chunk_index"],
                        chunk["text"],
                        normalize_for_search(chunk["text"]),
                        chunk["quote"],
                        chunk["chunk_index"],
                        f"{course_template.name} > {chunk['section_title']}",
                        chunk["section_title"],
                        chunk["topic_ids"],
                        chunk["content_hash"],
                        chunk["token_count"],
                        {"synthetic": True, "persona": user.persona_key},
                        created_at,
                    )
                else:
                    await conn.execute(
                        """
                        INSERT INTO document_chunks (
                            id, subject_id, source_id, user_id, filename, chunk_index, text,
                            normalized_text, quote, page, page_start, page_end, section_path,
                            section_title, topic_ids, content_hash, token_count, embedding_status,
                            metadata, created_at
                        )
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$10,$10,$11,$12,$13,$14,$15,'disabled',$16,$17)
                        """,
                        chunk["id"],
                        course_id,
                        source_id,
                        user.user_id,
                        filename,
                        chunk["chunk_index"],
                        chunk["text"],
                        normalize_for_search(chunk["text"]),
                        chunk["quote"],
                        chunk["chunk_index"],
                        f"{course_template.name} > {chunk['section_title']}",
                        chunk["section_title"],
                        chunk["topic_ids"],
                        chunk["content_hash"],
                        chunk["token_count"],
                        {"synthetic": True, "persona": user.persona_key},
                        created_at,
                    )

                if chunk["topic"].lesson_id:
                    await conn.execute(
                        """
                        INSERT INTO lesson_material_mappings (id, lesson_id, topic_id, source_id, chunk_id, confidence, reason, created_at)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                        """,
                        f"map_{uuid.uuid4().hex[:10]}",
                        chunk["topic"].lesson_id,
                        chunk["topic"].id,
                        source_id,
                        chunk["id"],
                        0.92,
                        "Synthetic seed alignment",
                        created_at,
                    )
    return {"source_id": source_id, "filename": filename, "chunks": chunks}


async def simulate_topic_history(
    pool: asyncpg.Pool,
    *,
    user: SeededUser,
    course_id: str,
    topic: Topic,
    topic_template: TopicTemplate,
    persona: PersonaTemplate,
    history_days: int,
    seed: int,
) -> dict[str, int]:
    rng = build_rng(seed, user.user_id, course_id, topic.id, "history")
    scheduler = get_scheduler(None)
    today = date.today()
    if topic.learning_state == "future" and not topic.practice_allowed:
        return {"sessions": 0, "correct": 0, "questions": 0}

    sessions = 3 if topic.learning_state == "taught" else 2 if topic.learning_state == "current" else 1
    if persona.performance_bias > 0.75:
        sessions += 1
    if topic_template.difficulty > 0.65:
        sessions += 1

    totals = {"sessions": 0, "correct": 0, "questions": 0}
    first_gap = max(3, history_days // (sessions + 1))

    for session_index in range(sessions):
        days_ago = max(1, history_days - first_gap * (session_index + 1) + rng.randint(-2, 2))
        review_day = today - timedelta(days=days_ago)
        review_time = utc_from_local_day(review_day, 13 + (session_index % 5), 15)
        source_type = (
            "entry_diagnostic_quiz"
            if session_index == 0 and topic.awaiting_diagnostic and topic.learning_state != "future"
            else ("system_quiz" if session_index % 2 == 0 else "workspace_quiz")
        )
        if topic.learning_state == "future" and topic.practice_allowed:
            source_type = "workspace_quiz"

        batch_size = 5 if source_type == "entry_diagnostic_quiz" else 3
        base_prob = (
            persona.performance_bias
            + float(topic.mastery or 0.0) * 0.18
            - topic_template.difficulty * 0.20
            + (0.06 if topic.learning_state == "taught" else 0.02 if topic.learning_state == "current" else -0.03)
            + rng.uniform(-0.07, 0.07)
        )
        p_correct = clamp(base_prob, 0.18, 0.93)
        question_format = "mcq_4" if session_index % 3 != 1 else "mcq_2"
        outcomes = [
            BatchQuestionOutcome(correct=rng.random() < p_correct, question_format=question_format)
            for _ in range(batch_size)
        ]

        previous_review = topic.fsrs_last_review
        previous_state = int(topic.fsrs_state or 0)
        source_id = f"synthetic:{user.user_id}:{course_id}:{topic.id}:{session_index}"
        await apply_objective_batch(
            pool,
            topic,
            user_id=user.user_id,
            subject_id=course_id,
            source_type=source_type,
            source_id=source_id,
            outcomes=outcomes,
            is_diagnostic=source_type == "entry_diagnostic_quiz",
        )
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE mastery_events SET created_at=$1 WHERE user_id=$2 AND source_id=$3",
                review_time,
                user.user_id,
                source_id,
            )

        rating = _batch_rating(outcomes)
        FSRSScheduler.update(topic, rating, review_day, scheduler)
        topic.fsrs_due_date = _due_date_from_card(topic)
        elapsed_days = max(0, (review_day - previous_review).days) if previous_review else 0
        await repository.append_review_log(
            pool,
            FsrsReviewLog(
                id=f"log-{uuid.uuid4()}",
                user_id=user.user_id,
                subject_id=course_id,
                item_id=topic.id,
                rating={"Again": 1, "Hard": 2, "Good": 3, "Easy": 4}[rating],
                review_date=review_time,
                elapsed_days=elapsed_days,
                review_state=previous_state,
            ),
        )
        await repository.update_topic(pool, topic)

        correct_count = sum(1 for outcome in outcomes if outcome.correct)
        totals["sessions"] += 1
        totals["correct"] += correct_count
        totals["questions"] += len(outcomes)

    return totals


async def seed_learning_history(
    pool: asyncpg.Pool,
    *,
    user: SeededUser,
    course_id: str,
    course_template: CourseTemplate,
    topics: list[Topic],
    persona: PersonaTemplate,
    history_days: int,
    seed: int,
) -> dict[str, int]:
    template_by_title = {topic_template.title: topic_template for topic_template in course_template.topics}
    totals = {"sessions": 0, "correct": 0, "questions": 0}
    for topic in topics:
        topic_totals = await simulate_topic_history(
            pool,
            user=user,
            course_id=course_id,
            topic=topic,
            topic_template=template_by_title[topic.title],
            persona=persona,
            history_days=history_days,
            seed=seed,
        )
        for key in totals:
            totals[key] += topic_totals[key]
    return totals


async def seed_practice_artifacts(
    pool: asyncpg.Pool,
    *,
    user: SeededUser,
    course_id: str,
    course_template: CourseTemplate,
    topics: list[Topic],
    chunk_bundle: dict[str, Any],
) -> None:
    topics_sorted = sorted(topics, key=lambda item: (item.mastery, item.title))
    weak_topics = topics_sorted[:2]
    if not weak_topics:
        return
    primary_topic = weak_topics[0]
    related_chunks = [chunk for chunk in chunk_bundle["chunks"] if primary_topic.id in chunk["topic_ids"]]
    quote = related_chunks[0]["quote"] if related_chunks else primary_topic.description
    source_ref = {
        "sourceId": chunk_bundle["source_id"],
        "filename": chunk_bundle["filename"],
        "sectionTitle": primary_topic.title,
        "chunkIds": [chunk["id"] for chunk in related_chunks] or [],
        "quote": quote,
    }
    questions = []
    for index in range(3):
        prompt = f"What is the key idea of {primary_topic.title}?"
        correct = primary_topic.description.split(".")[0]
        options = [
            correct,
            f"A distractor about {course_template.name}",
            "A partially correct but incomplete statement",
            "An unrelated definition",
        ]
        questions.append(
            {
                "id": f"question_{uuid.uuid4().hex[:10]}",
                "question": prompt,
                "options": options,
                "correctAnswer": correct,
                "explanation": quote,
                "topicId": primary_topic.id,
                "topicName": primary_topic.title,
                "sourceRef": source_ref,
            }
        )

    created_at = utc_from_local_day(date.today() - timedelta(days=1), 15, 30)
    async with pool.acquire() as conn:
        quiz_id = f"quiz_{uuid.uuid4().hex[:10]}"
        await conn.execute(
            """
            INSERT INTO practice_quizzes (id, subject_id, user_id, topic_id, title, difficulty, instructions, selected_source_ids, questions, created_at)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
            """,
            quiz_id,
            course_id,
            user.user_id,
            primary_topic.id,
            f"Synthetic quiz: {primary_topic.title}",
            "medium",
            "Synthetic practice set for eval.",
            [chunk_bundle["source_id"]],
            questions,
            created_at,
        )
        score = max(0, min(3, round(primary_topic.mastery * 3)))
        await conn.execute(
            """
            INSERT INTO practice_quiz_results (
                id, quiz_id, subject_id, user_id, score, total, accuracy_percent,
                average_seconds_per_question, mistakes, created_at
            )
            VALUES ($1,$2,$3,$4,$5,3,$6,$7,$8,$9)
            """,
            f"result_{uuid.uuid4().hex[:10]}",
            quiz_id,
            course_id,
            user.user_id,
            score,
            score * 33,
            42 + (3 - score) * 11,
            [{"question": questions[0]["question"], "selected": questions[1]["options"][1], "correct": questions[0]["correctAnswer"]}] if score < 3 else [],
            created_at + timedelta(minutes=16),
        )

        for topic in weak_topics:
            await conn.execute(
                """
                INSERT INTO flashcards (
                    id, subject_id, user_id, topic_id, front, back, explanation, source_ref, due_at, last_rating, created_at, updated_at
                )
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$11)
                """,
                f"flash_{uuid.uuid4().hex[:10]}",
                course_id,
                user.user_id,
                topic.id,
                f"Explain {topic.title}",
                topic.description,
                "Synthetic flashcard for review.",
                source_ref,
                created_at + timedelta(days=1),
                "Good" if topic.mastery > 0.6 else "Hard",
                created_at,
            )

        thread_id = f"thread_{uuid.uuid4().hex[:10]}"
        await conn.execute(
            """
            INSERT INTO chat_threads (id, subject_id, user_id, title, origin, created_at, updated_at)
            VALUES ($1,$2,$3,$4,'normal',$5,$6)
            """,
            thread_id,
            course_id,
            user.user_id,
            f"Review {primary_topic.title}",
            created_at - timedelta(minutes=10),
            created_at,
        )
        await conn.execute(
            """
            INSERT INTO chat_messages (id, thread_id, user_id, role, content, source_refs, actions, created_at)
            VALUES ($1,$2,$3,'user',$4,'[]'::jsonb,'[]'::jsonb,$5)
            """,
            f"msg_{uuid.uuid4().hex[:10]}",
            thread_id,
            user.user_id,
            f"Can you explain {primary_topic.title} more simply?",
            created_at - timedelta(minutes=10),
        )
        await conn.execute(
            """
            INSERT INTO chat_messages (id, thread_id, user_id, role, content, source_refs, actions, created_at)
            VALUES ($1,$2,$3,'assistant',$4,$5,$6,$7)
            """,
            f"msg_{uuid.uuid4().hex[:10]}",
            thread_id,
            user.user_id,
            f"{primary_topic.title} means: {quote}",
            [source_ref],
            [{"label": "Create 5 flashcards", "type": "generate_flashcards"}],
            created_at - timedelta(minutes=8),
        )


async def seed_historical_tasks(
    pool: asyncpg.Pool,
    *,
    user: SeededUser,
    course_id: str,
    topics: list[Topic],
    persona: PersonaTemplate,
) -> None:
    if not topics:
        return
    today = date.today()
    strong_topic = max(topics, key=lambda topic: topic.mastery)
    weak_topic = min(topics, key=lambda topic: topic.mastery)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO study_tasks (
                id, subject_id, topic_id, user_id, topic_title, type, duration_minutes, reason,
                scheduled_date, status, day, title, start_at, end_at, priority
            )
            VALUES ($1,$2,$3,$4,$5,'review',30,$6,$7,'done',$8,$9,$10,$11,'medium')
            """,
            f"task_{uuid.uuid4().hex[:10]}",
            course_id,
            strong_topic.id,
            user.user_id,
            strong_topic.title,
            "Synthetic completed review used to seed weekly progress.",
            today - timedelta(days=3),
            (today - timedelta(days=3)).strftime("%a"),
            f"Review: {strong_topic.title}",
            utc_from_local_day(today - timedelta(days=3), 12, 0),
            utc_from_local_day(today - timedelta(days=3), 12, 30),
        )
        if persona.missed_task_bias > 0.15:
            await conn.execute(
                """
                INSERT INTO study_tasks (
                    id, subject_id, topic_id, user_id, topic_title, type, duration_minutes, reason,
                    scheduled_date, status, day, title, start_at, end_at, priority
                )
                VALUES ($1,$2,$3,$4,$5,'review',30,$6,$7,'missed',$8,$9,$10,$11,'high')
                """,
                f"task_{uuid.uuid4().hex[:10]}",
                course_id,
                weak_topic.id,
                user.user_id,
                weak_topic.title,
                "Synthetic missed review to stress reschedule and warning flows.",
                today - timedelta(days=1),
                (today - timedelta(days=1)).strftime("%a"),
                f"Review: {weak_topic.title}",
                utc_from_local_day(today - timedelta(days=1), 13, 0),
                utc_from_local_day(today - timedelta(days=1), 13, 30),
            )


async def seed_user_courses(
    pool: asyncpg.Pool,
    *,
    user: SeededUser,
    persona: PersonaTemplate,
    history_days: int,
    seed: int,
) -> dict[str, int]:
    today = date.today()
    aggregate = {"questions": 0, "correct": 0, "sessions": 0}
    for course_index, course_template in enumerate(persona.courses):
        course_id, syllabus = await create_course_with_syllabus(
            pool,
            user,
            course_template,
            today=today,
            course_index=course_index,
        )
        user.course_ids.append(course_id)
        topics = await save_seed_topics(
            pool,
            user=user,
            course_id=course_id,
            course_template=course_template,
            syllabus=syllabus,
            persona=persona,
            seed=seed,
        )
        chunk_bundle = await seed_sources_and_chunks(
            pool,
            user=user,
            course_id=course_id,
            course_template=course_template,
            topics=topics,
            created_at=utc_from_local_day(today - timedelta(days=history_days + 2), 9, 0),
        )
        history_totals = await seed_learning_history(
            pool,
            user=user,
            course_id=course_id,
            course_template=course_template,
            topics=topics,
            persona=persona,
            history_days=history_days,
            seed=seed,
        )
        for key in aggregate:
            aggregate[key] += history_totals[key]
        refreshed_topics: list[Topic] = []
        for topic in topics:
            current = await repository.get_topic(pool, topic.id)
            if current:
                refreshed_topics.append(current)
        await seed_practice_artifacts(
            pool,
            user=user,
            course_id=course_id,
            course_template=course_template,
            topics=refreshed_topics,
            chunk_bundle=chunk_bundle,
        )
        await seed_historical_tasks(pool, user=user, course_id=course_id, topics=refreshed_topics, persona=persona)
    await build_unified_schedule(pool, user.user_id, today)
    return aggregate


def compute_auc(rows: list[tuple[float, int]]) -> float | None:
    positives = sum(actual for _, actual in rows)
    negatives = len(rows) - positives
    if positives == 0 or negatives == 0:
        return None

    sorted_rows = sorted(rows, key=lambda item: item[0])
    ranks: list[float] = [0.0] * len(sorted_rows)
    index = 0
    while index < len(sorted_rows):
        tie_end = index
        while tie_end < len(sorted_rows) and sorted_rows[tie_end][0] == sorted_rows[index][0]:
            tie_end += 1
        avg_rank = (index + 1 + tie_end) / 2.0
        for pos in range(index, tie_end):
            ranks[pos] = avg_rank
        index = tie_end

    positive_rank_sum = sum(rank for rank, row in zip(ranks, sorted_rows) if row[1] == 1)
    return (positive_rank_sum - positives * (positives + 1) / 2.0) / (positives * negatives)


async def build_summary(pool: asyncpg.Pool, users: list[SeededUser], output_dir: Path, *, prefix: str, history_days: int) -> dict[str, Any]:
    user_ids = [user.user_id for user in users]
    async with pool.acquire() as conn:
        counts = {
            "users": len(user_ids),
            "courses": await conn.fetchval("SELECT COUNT(*) FROM subjects WHERE user_id = ANY($1::text[])", user_ids),
            "topics": await conn.fetchval("SELECT COUNT(*) FROM topics WHERE user_id = ANY($1::text[])", user_ids),
            "sources": await conn.fetchval("SELECT COUNT(*) FROM course_sources WHERE user_id = ANY($1::text[])", user_ids),
            "chunks": await conn.fetchval("SELECT COUNT(*) FROM document_chunks WHERE user_id = ANY($1::text[])", user_ids),
            "tasks": await conn.fetchval("SELECT COUNT(*) FROM study_tasks WHERE user_id = ANY($1::text[])", user_ids),
            "mastery_events": await conn.fetchval("SELECT COUNT(*) FROM mastery_events WHERE user_id = ANY($1::text[])", user_ids),
            "review_logs": await conn.fetchval("SELECT COUNT(*) FROM fsrs_review_logs WHERE user_id = ANY($1::text[])", user_ids),
            "quizzes": await conn.fetchval("SELECT COUNT(*) FROM practice_quizzes WHERE user_id = ANY($1::text[])", user_ids),
            "flashcards": await conn.fetchval("SELECT COUNT(*) FROM flashcards WHERE user_id = ANY($1::text[])", user_ids),
            "chat_threads": await conn.fetchval("SELECT COUNT(*) FROM chat_threads WHERE user_id = ANY($1::text[])", user_ids),
        }
        event_rows = await conn.fetch(
            """
            SELECT predicted_p_correct, actual_correct, source_type
            FROM mastery_events
            WHERE user_id = ANY($1::text[]) AND NOT excluded
            ORDER BY created_at
            """,
            user_ids,
        )

    metric_rows = [(float(row["predicted_p_correct"]), 1 if row["actual_correct"] else 0) for row in event_rows]
    brier = mean((pred - actual) ** 2 for pred, actual in metric_rows) if metric_rows else 0.0
    rmse = brier ** 0.5
    avg_pred = mean(pred for pred, _ in metric_rows) if metric_rows else 0.0
    avg_actual = mean(actual for _, actual in metric_rows) if metric_rows else 0.0
    auc = compute_auc(metric_rows)

    by_source: dict[str, list[tuple[float, int]]] = {}
    for row in event_rows:
        by_source.setdefault(str(row["source_type"]), []).append((float(row["predicted_p_correct"]), 1 if row["actual_correct"] else 0))

    dashboards = []
    for user in users:
        dashboard = await course_svc.get_dashboard(pool, user.user_id)
        dashboards.append({"user": user, "dashboard": dashboard})

    avg_profile_metrics = {
        "knowledgeConsistency": round(mean(item["dashboard"]["profileMetrics"]["knowledgeConsistency"] for item in dashboards), 2),
        "retentionReliability": round(mean(item["dashboard"]["profileMetrics"]["retentionReliability"] for item in dashboards), 2),
        "personalCalibrationScore": round(mean(item["dashboard"]["profileMetrics"]["personalCalibrationScore"] for item in dashboards), 2),
        "calibrationGap": round(mean(item["dashboard"]["profileMetrics"]["calibrationGap"] for item in dashboards), 2),
        "engagementConfidence": round(mean(item["dashboard"]["profileMetrics"]["engagementConfidence"] for item in dashboards), 2),
    }

    per_user = []
    for item in dashboards:
        dashboard = item["dashboard"]
        profile_metrics = dashboard["profileMetrics"]
        event_count = int(profile_metrics.get("eventCount") or 0)
        per_user.append(
            {
                "username": item["user"].username,
                "email": item["user"].email,
                "password": item["user"].password,
                "persona": item["user"].persona_label,
                "courseCount": len(dashboard.get("courses") or []),
                "readiness": round(mean(course.get("readinessPercent", 0) for course in (dashboard.get("courses") or [{"readinessPercent": 0}])), 2),
                "eventCount": event_count,
                "knowledgeConsistency": profile_metrics["knowledgeConsistency"],
                "personalCalibrationScore": profile_metrics["personalCalibrationScore"],
                "retentionReliability": profile_metrics["retentionReliability"],
                "engagementConfidence": profile_metrics["engagementConfidence"],
            }
        )

    source_breakdown = []
    for source_type, rows in sorted(by_source.items()):
        src_brier = mean((pred - actual) ** 2 for pred, actual in rows) if rows else 0.0
        source_breakdown.append(
            {
                "sourceType": source_type,
                "count": len(rows),
                "rmse": round(src_brier ** 0.5, 4),
                "avgPredicted": round(mean(pred for pred, _ in rows), 4) if rows else 0.0,
                "avgActual": round(mean(actual for _, actual in rows), 4) if rows else 0.0,
            }
        )

    async with pool.acquire() as conn:
        warning_rows = await conn.fetch(
            "SELECT coverage_warning FROM subjects WHERE user_id = ANY($1::text[])",
            [user.user_id for user in users],
        )
    coverage_warning_count = sum(1 for row in warning_rows if row["coverage_warning"])
    over_budget_count = sum(1 for row in warning_rows if row["coverage_warning"] == "over_budget")
    warning_total = len(warning_rows)
    scheduler_metrics = {
        "totalCourses": warning_total,
        "coverageWarningCount": coverage_warning_count,
        "overBudgetWarningCount": over_budget_count,
        "overBudgetWarningRate": round((over_budget_count / warning_total), 4) if warning_total else 0.0,
    }

    summary = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "prefix": prefix,
        "historyDays": history_days,
        "counts": counts,
        "offlineMetrics": {
            "rmse": round(rmse, 4),
            "brier": round(brier, 4),
            "auc": round(auc, 4) if auc is not None else None,
            "avgPredicted": round(avg_pred, 4),
            "avgActual": round(avg_actual, 4),
            "calibrationGap": round(abs(avg_pred - avg_actual), 4),
        },
        "schedulerMetrics": scheduler_metrics,
        "avgProfileMetrics": avg_profile_metrics,
        "sourceBreakdown": source_breakdown,
        "users": per_user,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "synthetic_cohort.json"
    md_path = output_dir / "synthetic_cohort.md"
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    md_lines = [
        "# Synthetic Eval Cohort",
        "",
        f"Generated at: `{summary['generatedAt']}`",
        f"Prefix: `{prefix}`",
        f"History window: `{history_days}` days",
        "",
        "## Counts",
        "",
    ]
    for key, value in counts.items():
        md_lines.append(f"- `{key}`: {value}")

    metrics = summary["offlineMetrics"]
    md_lines.extend([
        "",
        "## Offline Metrics",
        "",
        f"- `RMSE`: {metrics['rmse']}",
        f"- `Brier`: {metrics['brier']}",
        f"- `AUC`: {metrics['auc'] if metrics['auc'] is not None else 'n/a'}",
        f"- `Avg predicted`: {metrics['avgPredicted']}",
        f"- `Avg actual`: {metrics['avgActual']}",
        f"- `Calibration gap`: {metrics['calibrationGap']}",
        "",
        "## Scheduler Metrics",
        "",
        f"- `Total courses`: {scheduler_metrics['totalCourses']}",
        f"- `Coverage warning count`: {scheduler_metrics['coverageWarningCount']}",
        f"- `Over-budget warning count`: {scheduler_metrics['overBudgetWarningCount']}",
        f"- `Over-budget warning rate`: {scheduler_metrics['overBudgetWarningRate']}",
        "",
        "## Avg Profile Metrics",
        "",
    ])
    for key, value in avg_profile_metrics.items():
        md_lines.append(f"- `{key}`: {value}")

    md_lines.extend([
        "",
        "## Source Breakdown",
        "",
        "| Source | Count | RMSE | Avg Predicted | Avg Actual |",
        "| --- | ---: | ---: | ---: | ---: |",
    ])
    for row in source_breakdown:
        md_lines.append(
            f"| {row['sourceType']} | {row['count']} | {row['rmse']} | {row['avgPredicted']} | {row['avgActual']} |"
        )

    md_lines.extend([
        "",
        "## Sample Users",
        "",
        "| Username | Password | Persona | Courses | Events | Consistency | Calibration | Retention |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ])
    for row in per_user:
        md_lines.append(
            f"| {row['username']} | {row['password']} | {row['persona']} | {row['courseCount']} | "
            f"{row['eventCount']} | {row['knowledgeConsistency']} | {row['personalCalibrationScore']} | {row['retentionReliability']} |"
        )
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    return summary


async def seed_synthetic_cohort(
    *,
    users: int,
    prefix: str,
    password: str,
    history_days: int,
    reset: bool,
    cleanup_only: bool,
    output_dir: Path,
    seed: int,
) -> dict[str, Any]:
    await init_pool()
    pool = get_pool()
    try:
        await ensure_prerequisites(pool)
        deleted = await cleanup_synthetic_users(pool, prefix) if reset else 0
        if cleanup_only:
            return {
                "generatedAt": datetime.now(timezone.utc).isoformat(),
                "prefix": prefix,
                "historyDays": history_days,
                "deletedUsersOnReset": deleted,
                "counts": {
                    "users": 0,
                    "courses": 0,
                    "topics": 0,
                    "sources": 0,
                    "chunks": 0,
                    "tasks": 0,
                    "mastery_events": 0,
                    "review_logs": 0,
                    "quizzes": 0,
                    "flashcards": 0,
                    "chat_threads": 0,
                },
                "offlineMetrics": {
                    "rmse": 0.0,
                    "brier": 0.0,
                    "auc": None,
                    "avgPredicted": 0.0,
                    "avgActual": 0.0,
                    "calibrationGap": 0.0,
                },
                "schedulerMetrics": {
                    "totalCourses": 0,
                    "coverageWarningCount": 0,
                    "overBudgetWarningCount": 0,
                    "overBudgetWarningRate": 0.0,
                },
                "avgProfileMetrics": {
                    "knowledgeConsistency": 0.0,
                    "retentionReliability": 0.0,
                    "personalCalibrationScore": 0.0,
                    "calibrationGap": 0.0,
                    "engagementConfidence": 0.0,
                },
                "sourceBreakdown": [],
                "users": [],
            }

        seeded_users: list[SeededUser] = []
        for index in range(users):
            persona = choose_persona(index)
            user = await create_synthetic_user(pool, prefix=prefix, persona=persona, index=index, password=password)
            learning_totals = await seed_user_courses(
                pool,
                user=user,
                persona=persona,
                history_days=history_days,
                seed=seed,
            )
            profile = await repository.get_profile(pool, user.user_id)
            if profile:
                await repository.update_profile(
                    pool,
                    user.user_id,
                    xp=profile.xp + learning_totals["correct"] * 10,
                    streak=max(profile.streak, min(history_days, safe_int(learning_totals["sessions"] / 2))),
                )
            seeded_users.append(user)

        summary = await build_summary(pool, seeded_users, output_dir, prefix=prefix, history_days=history_days)
        summary["deletedUsersOnReset"] = deleted
        return summary
    finally:
        await close_pool()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed a synthetic StudyFlow cohort for self-evaluation.")
    parser.add_argument("--users", type=int, default=6, help="Number of synthetic users to seed.")
    parser.add_argument("--history-days", type=int, default=28, help="How many historical days of study activity to simulate.")
    parser.add_argument("--prefix", default="synthetic-eval", help="Username/email prefix used for synthetic users.")
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help="Password assigned to all synthetic users.")
    parser.add_argument("--seed", type=int, default=20260707, help="Deterministic seed namespace for synthetic randomness.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory where synthetic cohort reports are written.")
    parser.add_argument("--reset", action="store_true", help="Delete existing synthetic users with the same prefix before seeding.")
    parser.add_argument("--cleanup-only", action="store_true", help="Only delete synthetic users matching the prefix, then exit.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = asyncio.run(
        seed_synthetic_cohort(
            users=max(1, args.users),
            prefix=args.prefix,
            password=args.password,
            history_days=max(7, args.history_days),
            reset=args.reset or args.cleanup_only,
            cleanup_only=args.cleanup_only,
            output_dir=Path(args.output_dir),
            seed=args.seed,
        )
    )
    if args.cleanup_only:
        print(f"Deleted synthetic users for prefix '{args.prefix}': {summary['deletedUsersOnReset']}")
        return 0
    print("Seeded synthetic cohort successfully.")
    print(f"Users: {summary['counts']['users']}")
    print(f"Courses: {summary['counts']['courses']}")
    print(f"Mastery events: {summary['counts']['mastery_events']}")
    print(f"RMSE: {summary['offlineMetrics']['rmse']}")
    print(f"Calibration gap: {summary['offlineMetrics']['calibrationGap']}")
    print(f"Report: {Path(args.output_dir) / 'synthetic_cohort.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
