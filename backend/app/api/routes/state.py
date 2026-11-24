from datetime import date

import asyncpg
from fastapi import APIRouter, Depends, Query

from app.api.deps import current_user_id
from app.db import repository
from app.db.pg_pool import get_pool
from app.services import course_api_service as course_dashboard_service
from app.services.scheduling_service import build_dashboard

router = APIRouter()


def _uid() -> str:
    return current_user_id()


@router.get("/api/state")
async def get_state(
    user_id: str | None = Query(None),
    subject_id: str | None = Query(None),
    pool: asyncpg.Pool = Depends(get_pool),
):
    del user_id
    uid = _uid()
    today = date.today()
    await _ensure_missed_tasks_marked(pool, uid, today)

    profile = await repository.get_profile(pool, uid)
    if not profile:
        return {"status": "error", "message": "Profile not found"}

    subjects = await repository.get_subjects(pool, uid)
    if not subject_id or subject_id not in subjects:
        subject_id = next(iter(subjects), None) if subjects else None

    dash = await build_dashboard(pool, uid, subject_id) if subject_id else None
    notifications = await repository.get_notifications(pool, uid)
    achievements = await repository.get_achievements(pool, uid)

    return {
        "status": "success",
        "profile": profile.model_dump(exclude={"plan_dirty"}),
        "dashboard": dash.model_dump() if dash else None,
        "notifications": notifications,
        "achievements": achievements,
    }


@router.get("/api/dashboard")
async def get_dashboard(
    user_id: str | None = Query(None),
    subject_id: str | None = Query(None),
    pool: asyncpg.Pool = Depends(get_pool),
):
    del user_id, subject_id
    uid = _uid()
    today = date.today()
    await _ensure_missed_tasks_marked(pool, uid, today)
    return await course_dashboard_service.get_dashboard(pool, uid)


@router.get("/api/plan/weekly")
async def weekly_plan(
    user_id: str | None = Query(None),
    subject_id: str | None = Query(None),
    pool: asyncpg.Pool = Depends(get_pool),
):
    del user_id
    uid = _uid()
    today = date.today()
    await _ensure_missed_tasks_marked(pool, uid, today)
    await repository.is_plan_dirty(pool, uid)

    subjects = await repository.get_subjects(pool, uid)
    if not subjects:
        return {"status": "success", "tasks": []}

    tasks = await repository.get_weekly_tasks_all_subjects(pool, uid, today)

    if subject_id and subject_id != "all":
        tasks = [t for t in tasks if t.subject_id == subject_id]

    tasks_list = []
    for task in tasks:
        subject = subjects.get(task.subject_id)
        task_dump = task.model_dump()
        task_dump["subjectName"] = subject.name if subject else ""
        tasks_list.append(task_dump)

    coverage_warning = None
    if subject_id and subject_id != "all" and subject_id in subjects:
        coverage_warning = subjects[subject_id].coverage_warning
    else:
        warnings = [subject.coverage_warning for subject in subjects.values() if subject.coverage_warning]
        coverage_warning = warnings[0] if warnings else None

    return {
        "status": "success",
        "coverageWarning": coverage_warning,
        "tasks": tasks_list,
    }


async def _ensure_missed_tasks_marked(pool, user_id: str, today: date) -> None:
    try:
        from app.services.unified_scheduler import ensure_missed_tasks_marked

        await ensure_missed_tasks_marked(pool, user_id, today)
    except ModuleNotFoundError:
        return


async def _build_unified_schedule(pool, user_id: str, today: date) -> dict:
    try:
        from app.services.unified_scheduler import build_unified_schedule

        return await build_unified_schedule(pool, user_id, today)
    except ModuleNotFoundError:
        return {"status": "success"}
