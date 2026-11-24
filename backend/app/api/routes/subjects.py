from datetime import date
import uuid

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.deps import current_user_id
from app.db import repository
from app.db.pg_pool import get_pool
from app.schemas.subject import Subject

router = APIRouter(prefix="/api/subjects")


def _uid() -> str:
    return current_user_id()


class SubjectBody(BaseModel):
    name: str
    mode: str = "semester"
    examDate: str | None = None
    weeklyGoalMinutes: int = 0
    dailyGoalMinutes: int = 30
    isPriority: bool = False


class ModeBody(BaseModel):
    mode: str


class RetuneBody(BaseModel):
    examDate: str | None = None
    mode: str | None = None


def subject_public_dump(subject: Subject) -> dict:
    data = subject.model_dump()
    if data.get("mode") == "exam_sprint":
        data["mode"] = "exam"
    return data


@router.get("")
async def list_subjects(user_id: str | None = Query(None), pool: asyncpg.Pool = Depends(get_pool)):
    del user_id
    uid = _uid()
    subjects = await repository.get_subjects(pool, uid)
    result = {}
    for subject_id, subject in subjects.items():
        subject_dump = subject_public_dump(subject)
        topics = await repository.get_topics(pool, subject_id)
        tasks = await repository.get_weekly_tasks(pool, uid, subject_id, date.today())
        subject_dump["topics"] = [topic.model_dump() for topic in topics]
        subject_dump["tasks"] = [task.model_dump() for task in tasks]
        result[subject_id] = subject_dump
    return {"status": "success", **result}


@router.post("")
async def create_subject(
    body: SubjectBody,
    user_id: str | None = Query(None),
    pool: asyncpg.Pool = Depends(get_pool),
):
    del user_id
    uid = _uid()
    subjects = await repository.get_subjects(pool, uid)
    if len(subjects) >= 10:
        raise HTTPException(400, "Má»—i ngÆ°á»i dÃ¹ng chá»‰ Ä‘Æ°á»£c táº¡o tá»‘i Ä‘a 10 mÃ´n há»c.")

    mode = "exam_sprint" if body.mode == "exam" else body.mode
    subject_id = f"subject-{uuid.uuid4().hex[:10]}"
    exam_date = date.fromisoformat(body.examDate) if body.examDate else None
    subject = Subject(
        id=subject_id,
        user_id=uid,
        name=body.name,
        mode=mode,
        exam_date=exam_date,
        weekly_goal_minutes=body.weeklyGoalMinutes,
        daily_goal_minutes=body.dailyGoalMinutes,
        is_priority=body.isPriority,
    )
    await repository.save_subject(pool, subject)
    await repository.set_plan_dirty(pool, uid, True)
    subject_dump = subject_public_dump(subject)
    subject_dump["topics"] = []
    subject_dump["tasks"] = []
    return {"status": "success", **subject_dump}


@router.post("/current/mode")
async def switch_mode(
    body: ModeBody,
    user_id: str | None = Query(None),
    pool: asyncpg.Pool = Depends(get_pool),
):
    del user_id
    uid = _uid()
    subjects = await repository.get_subjects(pool, uid)
    if not subjects:
        return {"status": "error", "message": "No subjects found"}
    subject_id = next(iter(subjects))
    mode = "exam_sprint" if body.mode == "exam" else body.mode
    await repository.update_subject(pool, subject_id, mode=mode)
    await repository.delete_future_tasks(pool, uid, subject_id, date.today())
    await repository.set_plan_dirty(pool, uid, True)
    subject = await repository.get_subject(pool, subject_id)
    subject_dump = subject_public_dump(subject) if subject else {}
    if subject:
        topics = await repository.get_topics(pool, subject_id)
        tasks = await repository.get_weekly_tasks(pool, uid, subject_id, date.today())
        subject_dump["topics"] = [topic.model_dump() for topic in topics]
        subject_dump["tasks"] = [task.model_dump() for task in tasks]
    return {"status": "success", **subject_dump}


@router.post("/current/retune")
async def retune_subject(
    body: RetuneBody,
    user_id: str | None = Query(None),
    pool: asyncpg.Pool = Depends(get_pool),
):
    del user_id
    uid = _uid()
    subjects = await repository.get_subjects(pool, uid)
    if not subjects:
        return {"status": "error", "message": "No subjects found"}
    subject_id = next(iter(subjects))

    fields: dict = {}
    if body.examDate:
        fields["exam_date"] = date.fromisoformat(body.examDate)
    if body.mode:
        fields["mode"] = "exam_sprint" if body.mode == "exam" else body.mode
    if fields:
        await repository.update_subject(pool, subject_id, **fields)

    await repository.delete_future_tasks(pool, uid, subject_id, date.today())
    await repository.set_plan_dirty(pool, uid, True)

    from app.services.scheduling_service import build_dashboard

    dashboard = await build_dashboard(pool, uid, subject_id)
    return {"status": "success", **dashboard.model_dump()}


class SubjectUpdateBody(BaseModel):
    name: str | None = None
    mode: str | None = None
    examDate: str | None = None
    dailyGoalMinutes: int | None = None
    isPriority: bool | None = None


@router.post("/{subject_id}/update")
async def update_specific_subject(
    subject_id: str,
    body: SubjectUpdateBody,
    user_id: str | None = Query(None),
    pool: asyncpg.Pool = Depends(get_pool),
):
    del user_id
    uid = _uid()
    fields = {}
    if body.name is not None:
        fields["name"] = body.name
    if body.mode is not None:
        fields["mode"] = "exam_sprint" if body.mode == "exam" else body.mode
    if body.examDate is not None:
        fields["exam_date"] = date.fromisoformat(body.examDate) if body.examDate else None
    if body.dailyGoalMinutes is not None:
        fields["daily_goal_minutes"] = body.dailyGoalMinutes
    if body.isPriority is not None:
        fields["is_priority"] = body.isPriority

    if fields:
        await repository.update_subject(pool, subject_id, **fields)
        await repository.delete_future_tasks(pool, uid, subject_id, date.today())
        await repository.set_plan_dirty(pool, uid, True)

    from app.services.scheduling_service import build_dashboard

    dashboard = await build_dashboard(pool, uid, subject_id)
    return {"status": "success", **dashboard.model_dump()}
