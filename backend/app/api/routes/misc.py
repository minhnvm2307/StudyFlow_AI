import asyncpg
from fastapi import APIRouter, Depends, Query

from app.api.deps import current_user_id
from app.config import settings
from app.core.document.llm_section_split import get_openai_client
from app.db import repository
from app.db.pg_pool import get_pool

router = APIRouter()


def _uid() -> str:
    return current_user_id()


@router.post("/api/chat")
async def chat(
    body: dict,
    user_id: str | None = Query(None),
    pool: asyncpg.Pool = Depends(get_pool),
):
    del user_id, pool
    messages = body.get("messages", [])
    try:
        client = get_openai_client()
        response = client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=messages,
            temperature=0.7,
        )
        content = response.choices[0].message.content
        return {
            "status": "success",
            "provider": "openai",
            "message": {"role": "assistant", "content": content},
            "sources": [],
        }
    except Exception:
        return {
            "status": "success",
            "provider": "mock",
            "message": {"role": "assistant", "content": "I'm here to help with your studies!"},
            "sources": [],
        }


@router.post("/api/settings")
async def update_settings(
    body: dict,
    user_id: str | None = Query(None),
    pool: asyncpg.Pool = Depends(get_pool),
):
    del user_id
    uid = _uid()
    allowed = {"mascot_tone", "quiet_hours"}
    fields = {key: value for key, value in body.items() if key in allowed}
    profile = await repository.update_profile(pool, uid, **fields)
    return {"status": "success", **profile.model_dump(exclude={"plan_dirty"})}


@router.post("/api/notifications/{notification_id}")
async def toggle_notification(
    notification_id: str,
    body: dict,
    user_id: str | None = Query(None),
    pool: asyncpg.Pool = Depends(get_pool),
):
    del user_id
    uid = _uid()
    profile = await repository.get_profile(pool, uid)
    if not profile:
        return {"status": "error", "message": "Profile not found"}
    notifications = dict(profile.notifications or {})
    notifications[notification_id] = {"enabled": body.get("enabled", True)}
    await repository.update_profile(pool, uid, notifications=notifications)
    return {"status": "success", "id": notification_id, "enabled": body.get("enabled", True)}


@router.post("/api/leaderboard/join")
async def join_leaderboard(
    user_id: str | None = Query(None),
    pool: asyncpg.Pool = Depends(get_pool),
):
    del user_id
    uid = _uid()
    profile = await repository.get_profile(pool, uid)
    xp = profile.xp if profile else 0
    return {
        "status": "success",
        "rank": 1,
        "entries": [{"name": uid, "xp": xp, "rank": 1}],
    }


@router.post("/api/after-class-content")
async def after_class_content(
    body: dict,
    user_id: str | None = Query(None),
    pool: asyncpg.Pool = Depends(get_pool),
):
    del user_id
    uid = _uid()
    subjects = await repository.get_subjects(pool, uid)
    subject_id = next(iter(subjects), None) if subjects else None
    if not subject_id:
        return {"status": "error", "message": "No subject found"}

    from datetime import date
    import fsrs
    import uuid

    from app.core.scheduler.bkt import BKTModel
    from app.schemas.task import StudyTask
    from app.schemas.topic import Topic

    topic_id = f"topic-afterclass-{uuid.uuid4().hex[:8]}"
    topic = Topic(
        id=topic_id,
        subject_id=subject_id,
        user_id=uid,
        title=body.get("title", "After-class content"),
        content_chunk=body.get("source", ""),
        mastery=BKTModel.DIAGNOSTIC_PRIORS["p_l0"],
        p_l0=BKTModel.DIAGNOSTIC_PRIORS["p_l0"],
        p_t=BKTModel.DIAGNOSTIC_PRIORS["p_t"],
        p_g=BKTModel.DIAGNOSTIC_PRIORS["p_g"],
        p_s=BKTModel.DIAGNOSTIC_PRIORS["p_s"],
        awaiting_diagnostic=True,
        fsrs_card=fsrs.Card().to_dict(),
    )
    await repository.save_topics(pool, [topic])

    task = StudyTask(
        id=f"task-afterclass-{topic_id}",
        subject_id=subject_id,
        user_id=uid,
        topic_id=topic_id,
        topic_title=topic.title,
        type="after_class",
        duration_minutes=15,
        reason="After-class content",
        scheduled_date=date.today(),
        status="ready",
    )
    await repository.insert_study_tasks(pool, [task.model_dump()])
    await repository.set_plan_dirty(pool, uid, True)
    return {"status": "success", "topic": topic.model_dump(), "task": task.model_dump()}
