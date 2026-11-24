from datetime import date

import asyncpg
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.deps import current_user_id
from app.db import repository
from app.db.pg_pool import get_pool
from app.services.scheduling_service import build_dashboard

router = APIRouter()


def _uid() -> str:
    return current_user_id()


class ExamPlanBody(BaseModel):
    examDate: str
    dailyMinutes: int = 30


@router.post("/api/exam-plan")
async def create_exam_plan(
    body: ExamPlanBody,
    user_id: str | None = Query(None),
    pool: asyncpg.Pool = Depends(get_pool),
):
    del user_id
    uid = _uid()
    subjects = await repository.get_subjects(pool, uid)
    if not subjects:
        return {"status": "error", "message": "No subjects found"}
    subject_id = next(iter(subjects))

    exam_date = date.fromisoformat(body.examDate)
    await repository.update_subject(
        pool,
        subject_id,
        mode="exam_sprint",
        exam_date=exam_date,
        daily_goal_minutes=body.dailyMinutes,
    )
    await repository.delete_future_tasks(pool, uid, subject_id, date.today())
    await repository.set_plan_dirty(pool, uid, True)

    dashboard = await build_dashboard(pool, uid, subject_id)
    return {"status": "success", **dashboard.model_dump()}


async def _build_unified_schedule(pool, user_id: str, today: date) -> dict:
    try:
        from app.services.unified_scheduler import build_unified_schedule

        return await build_unified_schedule(pool, user_id, today)
    except ModuleNotFoundError:
        return {"status": "success"}


@router.get("/api/readiness/checklist")
async def readiness_checklist(
    user_id: str | None = Query(None),
    subject_id: str | None = Query(None),
    pool: asyncpg.Pool = Depends(get_pool),
):
    del user_id
    uid = _uid()
    if not subject_id:
        subjects = await repository.get_subjects(pool, uid)
        subject_id = next(iter(subjects), None) if subjects else None
    if not subject_id:
        return {"status": "error", "message": "No subject found"}

    topics = await repository.get_topics(pool, subject_id)
    mastered = [topic for topic in topics if topic.mastery >= 0.85]
    weak = [topic for topic in topics if topic.mastery < 0.4]
    readiness = (len(mastered) / max(1, len(topics))) * 100

    items = [
        {"id": "topics_covered", "label": "All topics covered", "done": len(weak) == 0},
        {
            "id": "mastery_above_60",
            "label": "Average mastery > 60%",
            "done": (sum(topic.mastery for topic in topics) / max(1, len(topics))) >= 0.60,
        },
        {
            "id": "no_diagnostic_pending",
            "label": "No pending diagnostics",
            "done": all(not topic.awaiting_diagnostic for topic in topics),
        },
    ]
    return {
        "status": "success",
        "readiness": round(readiness, 1),
        "disclaimer": "Readiness is an estimate based on mastery scores.",
        "items": items,
    }


@router.post("/api/mock-test/complete")
async def mock_test_complete(
    user_id: str | None = Query(None),
    pool: asyncpg.Pool = Depends(get_pool),
):
    del user_id
    uid = _uid()
    subjects = await repository.get_subjects(pool, uid)
    subject_id = next(iter(subjects), None) if subjects else None
    if not subject_id:
        return {"status": "error", "message": "No subject found"}

    topics = await repository.get_topics(pool, subject_id)
    if not topics:
        return {"status": "error", "message": "No topics"}
    weakest = min(topics, key=lambda topic: topic.mastery)
    weakest.mastery = min(0.99, weakest.mastery + 0.06)
    weakest.cost_mins = 15 + round((1 - weakest.mastery) * 15)
    await repository.update_topic(pool, weakest)
    await repository.set_plan_dirty(pool, uid, True)
    return {"status": "success", "topicUpdated": weakest.model_dump()}


@router.post("/api/recovery/apply")
async def recovery_apply(
    body: dict | None = None,
    user_id: str | None = Query(None),
    pool: asyncpg.Pool = Depends(get_pool),
):
    del body, user_id
    uid = _uid()
    subjects = await repository.get_subjects(pool, uid)
    subject_id = next(iter(subjects), None) if subjects else None
    if not subject_id:
        return {"status": "error", "message": "No subject found"}

    today = date.today()
    tasks = await repository.get_weekly_tasks(pool, uid, subject_id, date(2000, 1, 1))
    for task in tasks:
        if task.status == "missed":
            task.duration_minutes = min(task.duration_minutes, 20)
            task.scheduled_date = today
            task.status = "ready"
            await repository.update_task_status(pool, task.id, "ready")

    await repository.set_plan_dirty(pool, uid, True)
    dashboard = await build_dashboard(pool, uid, subject_id)
    return {"status": "success", **dashboard.model_dump()}
