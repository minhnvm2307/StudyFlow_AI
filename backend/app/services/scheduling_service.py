"""High-level scheduling helpers: dashboard builder, budget rescale, retune."""
from __future__ import annotations

from datetime import date

import asyncpg

from app.db import repository
from app.schemas.task import Dashboard


async def get_or_build_today_tasks(
    pool: asyncpg.Pool, user_id: str, subject_id: str
) -> list:
    tasks = await repository.get_weekly_tasks(pool, user_id, subject_id, date.today())
    today = date.today()
    today_ready = [t for t in tasks if t.scheduled_date == today and t.status == "ready"]
    if not today_ready:
        # Trigger rebuild only if plan is dirty
        dirty = await repository.is_plan_dirty(pool, user_id)
        if dirty:
            from app.services.unified_scheduler import build_unified_schedule
            await build_unified_schedule(pool, user_id, today)
            tasks = await repository.get_weekly_tasks(pool, user_id, subject_id, today)
    return [t for t in tasks if t.scheduled_date == today]


async def build_dashboard(
    pool: asyncpg.Pool, user_id: str, subject_id: str
) -> Dashboard:
    today_tasks = await get_or_build_today_tasks(pool, user_id, subject_id)
    profile = await repository.get_profile(pool, user_id)
    subject = await repository.get_subject(pool, subject_id)
    topics = await repository.get_topics(pool, subject_id)

    avg_mastery = (sum(t.mastery for t in topics) / len(topics) * 100) if topics else 0.0
    readiness = max(20.0, avg_mastery - 5.0) if subject and subject.mode == "exam_sprint" else avg_mastery
    coverage_warning = subject.coverage_warning if subject else None
    mascot_message = (
        "Your exam plan focuses on weak, high-impact topics."
        if subject and subject.mode == "exam_sprint"
        else "Daily budget split across all your subjects by urgency."
    )

    subject_dump = None
    if subject:
        subject_dump = subject.model_dump()
        if subject_dump.get("mode") == "exam_sprint":
            subject_dump["mode"] = "exam"
        tasks = await repository.get_weekly_tasks(pool, user_id, subject_id, date.today())
        subject_dump["topics"] = [t.model_dump() for t in topics]
        subject_dump["tasks"] = [t.model_dump() for t in tasks]

    return Dashboard(
        subject=subject_dump,
        readiness=round(readiness, 1),
        streak=profile.streak if profile else 0,
        xp=profile.xp if profile else 0,
        today_tasks=[t.model_dump() for t in today_tasks],
        coverage_warning=coverage_warning,
        mascot_message=mascot_message,
    )


async def rescale_today_budget(
    pool: asyncpg.Pool, user_id: str, subject_id: str, new_budget: int
) -> list:
    """Slice today's ready tasks to fit new budget — no FSRS/BKT calls."""
    from app.core.scheduler.urgency import PriorityScheduler
    tasks = await repository.get_weekly_tasks(pool, user_id, subject_id, date.today())
    today = date.today()
    today_tasks = [t for t in tasks if t.scheduled_date == today and t.status == "ready"]
    sliced = PriorityScheduler().slice_session(today_tasks, new_budget)
    return sliced
