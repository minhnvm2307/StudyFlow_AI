import uuid
from datetime import date

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import current_user_id
from app.db import repository
from app.db.pg_pool import get_pool
from app.schemas.session import QuizAnswer, QuizQuestion, QuizSession
from app.services.review_service import process_session_submission
from app.services.scheduling_service import rescale_today_budget

router = APIRouter()


def _uid() -> str:
    return current_user_id()


@router.post("/api/tasks/{task_id}/session")
async def create_session(
    task_id: str,
    user_id: str | None = Query(None),
    force_regenerate: bool = Query(False),
    pool: asyncpg.Pool = Depends(get_pool),
):
    del user_id
    uid = _uid()
    subjects = await repository.get_subjects(pool, uid)
    task = None
    for subject_id in subjects:
        tasks = await repository.get_weekly_tasks(pool, uid, subject_id, date(2000, 1, 1))
        task = next((item for item in tasks if item.id == task_id), None)
        if task:
            break
    if not task:
        raise HTTPException(404, "Task not found")

    topic = await repository.get_topic(pool, task.topic_id)
    if not topic:
        raise HTTPException(404, "Topic not found")

    is_diagnostic = task.type == "diagnostic" or topic.awaiting_diagnostic
    num_questions = 5 if is_diagnostic else 3

    use_existing = False
    past_questions = []
    if not force_regenerate:
        past_questions = await repository.get_recent_topic_questions(pool, topic.id, uid, num_questions)
        if len(past_questions) >= num_questions:
            use_existing = True

    session_id = f"session-{uuid.uuid4()}"
    questions = []

    if use_existing:
        for index, question in enumerate(past_questions[:num_questions]):
            questions.append(
                QuizQuestion(
                    id=f"{topic.id}-q{index + 1}",
                    session_id=session_id,
                    topic_id=topic.id,
                    user_id=uid,
                    prompt=question.prompt,
                    options=question.options,
                    correct_option=question.correct_option,
                    explanation=question.explanation,
                    source=question.source,
                )
            )
    else:
        raw_questions = _build_local_quiz(topic.title, topic.content_chunk, num_questions)
        for index, question in enumerate(raw_questions):
            options = question["options"]
            questions.append(
                QuizQuestion(
                    id=f"{topic.id}-q{index + 1}",
                    session_id=session_id,
                    topic_id=topic.id,
                    user_id=uid,
                    prompt=question["question"],
                    options=options,
                    correct_option=options[0],
                    explanation=question["explanation"],
                )
            )

    session = QuizSession(
        id=session_id,
        subject_id=task.subject_id,
        task_id=task_id,
        user_id=uid,
        is_diagnostic=is_diagnostic,
        questions=questions,
    )
    await repository.save_quiz_session(pool, session)
    return {"status": "success", **session.model_dump()}


def _build_local_quiz(section_title: str, content_chunk: str, count: int) -> list[dict]:
    text = " ".join((content_chunk or section_title or "this topic").split())
    excerpt = text[:180] or section_title or "this topic"
    topic = section_title or "this topic"
    templates = [
        (f"Which statement is supported by the material about {topic}?", excerpt),
        (f"What is the best summary of {topic}?", excerpt),
        (f"Which detail should you remember for {topic}?", excerpt),
        (f"What should you review first in {topic}?", excerpt),
        (f"Which option matches the source content for {topic}?", excerpt),
    ]
    questions = []
    for index in range(count):
        prompt, correct = templates[index % len(templates)]
        questions.append(
            {
                "question": prompt,
                "options": [
                    correct,
                    "The material says this topic can be skipped.",
                    "The material gives no relevant information.",
                    "The material contradicts the course objective.",
                ],
                "explanation": correct,
            }
        )
    return questions


@router.post("/api/sessions/{session_id}/submit")
async def submit_session(
    session_id: str,
    body: dict,
    user_id: str | None = Query(None),
    pool: asyncpg.Pool = Depends(get_pool),
):
    del user_id
    uid = _uid()
    answers_raw = body.get("answers", [])
    rating = body.get("rating")
    answers = [QuizAnswer(**answer) for answer in answers_raw]
    try:
        result = await process_session_submission(pool, uid, session_id, answers, manual_rating=rating)
    except ValueError as error:
        return {"status": "error", "message": str(error)}
    return {"status": "success", **result.model_dump()}


@router.post("/api/session/update-budget")
async def update_budget(
    body: dict,
    user_id: str | None = Query(None),
    pool: asyncpg.Pool = Depends(get_pool),
):
    del user_id
    uid = _uid()
    new_budget = body.get("dailyGoalMinutes", 30)
    subjects = await repository.get_subjects(pool, uid)
    subject_id = next(iter(subjects), None) if subjects else None
    if not subject_id:
        return {"status": "error", "message": "No subject found"}
    sliced = await rescale_today_budget(pool, uid, subject_id, new_budget)
    return {"status": "success", "todayTasks": [task.model_dump() for task in sliced]}
