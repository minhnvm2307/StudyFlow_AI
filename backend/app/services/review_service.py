from __future__ import annotations

from datetime import date, datetime, timezone
import uuid
from collections import defaultdict

import asyncpg

from app.config import settings
from app.core.scheduler import FSRSScheduler, get_scheduler
from app.db import repository
from app.schemas import FsrsReviewLog, QuizAnswer, SessionResult
from app.services.mastery_service import BatchQuestionOutcome, apply_objective_batch

RATING_TO_INT = {"Again": 1, "Hard": 2, "Good": 3, "Easy": 4}


async def process_session_submission(
    pool: asyncpg.Pool,
    user_id: str,
    session_id: str,
    answers: list[QuizAnswer],
    manual_rating: str | None = None,
) -> SessionResult:
    session = await repository.get_quiz_session(pool, session_id)
    if not session:
        raise ValueError("Quiz session not found")

    profile = await repository.get_profile(pool, user_id)
    if not profile:
        raise ValueError("Profile not found")

    scheduler = get_scheduler(profile.fsrs_custom_weights)
    task = await repository.get_task(pool, user_id, session.task_id)
    is_new_task = bool(task and task.type == "new")
    answer_by_id = {answer.question_id: answer for answer in answers}
    correct_count = 0
    topic_before: dict[str, float] = {}
    topic_cache: dict[str, object] = {}
    today = date.today()
    total_questions = len(session.questions)
    source_type = "entry_diagnostic_quiz" if session.is_diagnostic else "system_quiz"

    batch_outcomes: dict[str, list[BatchQuestionOutcome]] = defaultdict(list)

    for question in session.questions:
        answer = answer_by_id.get(question.id)
        if not answer:
            continue

        primary_topic = topic_cache.get(question.topic_id)
        if primary_topic is None:
            primary_topic = await repository.get_topic(pool, question.topic_id)
            if not primary_topic:
                continue
            topic_cache[question.topic_id] = primary_topic
        scoped_topics = await _scoped_subtopics_for_task(pool, task, primary_topic)
        correct = answer.selected_option == question.correct_option
        if correct:
            correct_count += 1
        question_format = "mcq_4" if len(question.options or []) == 4 else ("mcq_2" if len(question.options or []) == 2 else ("fill_blank" if not question.options else f"mcq_{len(question.options)}"))
        targets = [primary_topic, *scoped_topics]
        for target in targets:
            topic_cache[target.id] = target
            topic_before.setdefault(target.id, target.mastery)
            batch_outcomes[target.id].append(BatchQuestionOutcome(correct=correct, question_format=question_format))

    for question in session.questions:
        answer = answer_by_id.get(question.id)
        if not answer:
            continue
        correct = answer.selected_option == question.correct_option
        await repository.update_quiz_question(pool, question.id, answer.selected_option, correct)

    for topic_id, outcomes in batch_outcomes.items():
        topic = topic_cache[topic_id]
        previous_review = topic.fsrs_last_review
        previous_state = int(topic.fsrs_state or 0)
        batch_id = f"{session.id}:{topic_id}"
        await apply_objective_batch(
            pool,
            topic,
            user_id=profile.id,
            subject_id=session.subject_id,
            source_type=source_type,
            source_id=batch_id,
            outcomes=outcomes,
            is_diagnostic=session.is_diagnostic,
        )
        if is_new_task:
            topic.is_learned = True
        rating = _normalize_rating(manual_rating) or _batch_rating(outcomes)
        FSRSScheduler.update(topic, rating, today, scheduler)
        topic.fsrs_due_date = _due_date_from_card(topic)
        elapsed_days = max(0, (today - previous_review).days) if previous_review else 0
        await repository.append_review_log(pool, FsrsReviewLog(
            id=f"log-{uuid.uuid4()}",
            user_id=profile.id,
            subject_id=session.subject_id,
            item_id=topic.id,
            rating=RATING_TO_INT[rating],
            review_date=datetime.now(timezone.utc),
            elapsed_days=elapsed_days,
            review_state=previous_state,
        ))
        await repository.update_topic(pool, topic)

    mastery_delta = []
    for topic_id, before in topic_before.items():
        topic = await repository.get_topic(pool, topic_id)
        if topic:
            mastery_delta.append({"topicId": topic_id, "before": before, "after": topic.mastery, "delta": round((topic.mastery - before) * 100)})

    xp_earned = correct_count * settings.XP_PER_CORRECT_ANSWER
    await repository.update_profile(
        pool,
        user_id,
        xp=profile.xp + xp_earned,
        streak=profile.streak + 1 if total_questions > 0 and correct_count == total_questions else profile.streak,
    )
    await repository.update_session_result(
        pool,
        session_id,
        correct_count,
        total_questions,
        xp_earned,
        f"You answered {correct_count}/{total_questions} correctly!",
    )
    await repository.update_task_status(pool, session.task_id, "done")
    await repository.set_plan_dirty(pool, user_id, True)

    from app.services.unified_scheduler import build_unified_schedule
    await build_unified_schedule(pool, user_id, today)
    next_task = await _next_task(pool, user_id)

    return SessionResult(
        session_id=session_id,
        correct=correct_count,
        total=total_questions,
        xp_earned=xp_earned,
        mastery_delta=mastery_delta,
        next_task=next_task,
        feedback=f"You answered {correct_count}/{total_questions} correctly!",
    )


def _normalize_rating(value: str | None) -> str | None:
    if not value:
        return None
    lookup = {key.lower(): key for key in RATING_TO_INT}
    return lookup.get(str(value).lower())


def _due_date_from_card(topic) -> date | None:
    due = topic.fsrs_card.get("due") or topic.fsrs_card.get("due_date")
    if not due:
        return topic.fsrs_due_date
    try:
        return datetime.fromisoformat(str(due).replace("Z", "+00:00")).date()
    except Exception:
        return topic.fsrs_due_date


async def _scoped_subtopics_for_task(pool: asyncpg.Pool, task, topic) -> list:
    if not task or not task.parent_topic_id or topic.is_subtopic:
        return []
    topics = await repository.get_topics(pool, task.subject_id)
    children = [
        candidate for candidate in topics
        if candidate.is_subtopic and candidate.parent_topic_id == task.parent_topic_id and candidate.id != topic.id
    ]
    if task.scope == "partial_topic" and task.lesson_id:
        return [child for child in children if child.lesson_id == task.lesson_id]
    return children if task.scope == "topic" else []


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
async def _next_task(pool: asyncpg.Pool, user_id: str) -> dict | None:
    from app.services.course_api_service import list_tasks

    tasks = await list_tasks(pool, {"start": date.today().isoformat()}, user_id)
    for task in tasks:
        if task.get("status") in {"ready", "todo", "rescheduled"}:
            return task
    return None
