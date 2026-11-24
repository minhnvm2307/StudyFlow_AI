"""PostgreSQL-backed unified scheduler for StudyFlow.

The public entrypoints in this module are intentionally thin and stable:
``ensure_missed_tasks_marked(pool, user_id, today)``,
``build_unified_schedule(pool, user_id, today)``, and
``build_schedule_from_inputs(request)``.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import json
from typing import Any, TypeVar
from zoneinfo import ZoneInfo

import asyncpg

from app.config import settings
from app.core.cp_solver.coverage_pass import solve_coverage_pass
from app.core.scheduler import FSRSScheduler, PriorityScheduler, get_scheduler
from app.db import repository
from app.schemas import StudyTask, Subject, Topic, UserProfile
from app.services.mastery_service import simulate_objective_success

T = TypeVar("T")
APP_TZ = ZoneInfo("Asia/Bangkok")
GENERATED_TYPES = {"review", "recovery", "interleaved_session"}
LEGACY_GENERATED_TYPES = GENERATED_TYPES | {"new", "preview"}
ACTIVE_TASK_STATUSES = {"ready", "todo", "rescheduled"}
CP_EXTENSION_DAYS = 90
REVIEW_TASK_MINUTES = 30
MAX_CONTINUOUS_REVIEW_BLOCKS_PER_DAY = 2
MIN_CONTINUOUS_REVIEW_SPACING_DAYS = 2
SIMULATED_FUTURE_QUIZ_TOTAL_QUESTIONS = 20
SIMULATED_FUTURE_QUIZ_CORRECT_QUESTIONS = 16
SPRINT_REVIEW_WEAK_SPACING_DAYS = 1
SPRINT_REVIEW_MEDIUM_SPACING_DAYS = 2
SPRINT_REVIEW_STRONG_SPACING_DAYS = 4
SPRINT_REVIEW_BUDGET_CAP_MINUTES = 120
TOPIC_REVIEW_MASTERY_THRESHOLD = 0.60


@dataclass
class ScheduledBlock:
    task: StudyTask
    weight: float = 1.0
    scope_child_ids: tuple[str, ...] = ()


@dataclass
class CoverageTopicItem:
    id: str
    topic: Topic
    earliest_offset: int
    lesson_id: str | None = None
    scope_child_ids: tuple[str, ...] = ()


@dataclass
class ScheduleInput:
    """Pure scheduler request.

    ``fixed_blocks`` is where callers pass class meetings, unavailable events,
    sleep, or existing tasks that the rebuilt schedule must avoid.
    """

    user_id: str
    today: date
    profile: UserProfile
    subjects: Mapping[str, Subject]
    topic_map: Mapping[str, Sequence[Topic]]
    horizon: int
    daily_budget: int
    start_hhmm: tuple[int, int]
    study_days_map: Sequence[bool] | None = None
    reserved_minutes_by_day: Mapping[int, int] | None = None
    fixed_blocks: Sequence[ScheduledBlock] = ()
    allow_sprint_overflow: bool = False


@dataclass
class ScheduleResult:
    status: str
    blocks: list[ScheduledBlock]
    coverage_result: dict[str, Any]
    coverage_warning: str | None = None

    def task_dicts(self) -> list[dict[str, Any]]:
        return [block.task.model_dump() for block in self.blocks]


def build_schedule_from_inputs(request: ScheduleInput) -> ScheduleResult:
    """Build a display-ready study schedule from normalized in-memory inputs.

    This is the reusable core for initial generation and reschedule. Database
    callers should load inputs, call this function, then persist ``blocks``.
    """
    subjects = dict(request.subjects)
    topic_map = {subject_id: list(topics) for subject_id, topics in request.topic_map.items()}
    fixed_blocks = list(request.fixed_blocks)
    study_days_map = list(request.study_days_map or [
        _any_subject_studies(request.today + timedelta(days=offset), subjects.values(), request.profile)
        for offset in range(request.horizon)
    ])
    reserved_minutes_by_day = dict(request.reserved_minutes_by_day or {})

    coverage_blocks, coverage_result = _build_coverage_blocks(
        request.user_id,
        request.today,
        subjects,
        topic_map,
        request.profile,
        request.daily_budget,
        request.horizon,
        study_days_map,
        request.start_hhmm,
        reserved_minutes_by_day,
        fixed_blocks,
    )
    if coverage_result.get("status") != "success":
        return ScheduleResult("success", [], {"status": "success", "is_over_budget": True}, "over_budget")

    review_blocks = _build_review_blocks(
        request.user_id,
        request.today,
        subjects,
        topic_map,
        request.profile,
        request.daily_budget,
        request.horizon,
        coverage_blocks,
        request.start_hhmm,
        reserved_minutes_by_day,
        fixed_blocks,
        allow_sprint_overflow=request.allow_sprint_overflow,
    )
    coverage_warning = "over_budget" if coverage_result.get("is_over_budget") else None
    return ScheduleResult(
        status="success",
        blocks=[*coverage_blocks, *review_blocks],
        coverage_result=coverage_result,
        coverage_warning=coverage_warning,
    )


async def ensure_missed_tasks_marked(pool: asyncpg.Pool, user_id: str, today: date) -> None:
    """Mark past uncompleted work as missed before schedule reads/builds."""
    for status in ("ready", "todo"):
        tasks = await repository.get_tasks_before_date_with_status(pool, user_id, today, status)
        await repository.bulk_update_task_status(pool, [task.id for task in tasks], "missed")


async def build_unified_schedule(pool: asyncpg.Pool, user_id: str, today: date | None = None) -> dict[str, Any]:
    """Rebuild generated future tasks for all subjects owned by a user."""
    today = today or date.today()
    async with pool.acquire() as lock_conn:
        locked = await lock_conn.fetchval("SELECT pg_try_advisory_lock(hashtext($1))", user_id)
        if not locked:
            return {"status": "locked"}
        try:
            return await _build_unified_schedule_locked(pool, user_id, today)
        finally:
            await lock_conn.execute("SELECT pg_advisory_unlock(hashtext($1))", user_id)

async def build_subject_schedule(
    pool: asyncpg.Pool,
    user_id: str,
    subject_id: str,
    today: date | None = None,
    preferred_start_time: str | None = None,
) -> dict[str, Any]:
    """Rebuild generated future tasks for one subject without moving other subjects."""
    today = today or date.today()
    async with pool.acquire() as lock_conn:
        locked = await lock_conn.fetchval("SELECT pg_try_advisory_lock(hashtext($1))", user_id)
        if not locked:
            return {"status": "locked"}
        try:
            return await _build_subject_schedule_locked(pool, user_id, subject_id, today, preferred_start_time)
        finally:
            await lock_conn.execute("SELECT pg_advisory_unlock(hashtext($1))", user_id)

async def build_selected_subjects_schedule(
    pool: asyncpg.Pool,
    user_id: str,
    subject_ids: Sequence[str],
    today: date | None = None,
) -> dict[str, Any]:
    """Rebuild generated future tasks for selected subjects while keeping other subjects fixed."""
    today = today or date.today()
    normalized_subject_ids = [subject_id for subject_id in dict.fromkeys(subject_ids) if subject_id]
    if not normalized_subject_ids:
        return {"status": "success", "tasks": []}
    async with pool.acquire() as lock_conn:
        locked = await lock_conn.fetchval("SELECT pg_try_advisory_lock(hashtext($1))", user_id)
        if not locked:
            return {"status": "locked"}
        try:
            return await _build_selected_subjects_schedule_locked(pool, user_id, normalized_subject_ids, today)
        finally:
            await lock_conn.execute("SELECT pg_advisory_unlock(hashtext($1))", user_id)


async def _build_unified_schedule_locked(pool: asyncpg.Pool, user_id: str, today: date) -> dict[str, Any]:
    await ensure_missed_tasks_marked(pool, user_id, today)
    profile = await repository.get_profile(pool, user_id)
    if not profile:
        return {"status": "error", "message": "Profile not found"}

    subjects = await repository.get_subjects(pool, user_id)
    if not subjects:
        await repository.set_plan_dirty(pool, user_id, False)
        return {"status": "success", "tasks": []}

    topic_map = {
        subject_id: await repository.get_topics(pool, subject_id)
        for subject_id in subjects
    }
    horizon = _planning_horizon(today, subjects.values())
    study_days_map = [_any_subject_studies(today + timedelta(days=offset), subjects.values(), profile) for offset in range(horizon)]
    daily_budget = max(0, int(profile.daily_goal_minutes or settings.DEFAULT_DAILY_GOAL_MINUTES))
    start_hhmm = _preferred_start_time(profile)
    busy_event_blocks = await _busy_event_blocks(pool, user_id, today, horizon)
    class_blocks = await _class_meeting_blocks(pool, user_id, today, horizon)
    busy_blocks = [*busy_event_blocks, *class_blocks]
    reserved_minutes_by_day = _with_window_capacity_adjustments(
        today,
        horizon,
        subjects.values(),
        profile,
        daily_budget,
        _busy_reserved_minutes_by_day(today, horizon, busy_blocks, subjects.values(), profile),
    )

    schedule = build_schedule_from_inputs(ScheduleInput(
        user_id=user_id,
        today=today,
        profile=profile,
        subjects=subjects,
        topic_map=topic_map,
        horizon=horizon,
        daily_budget=daily_budget,
        start_hhmm=start_hhmm,
        study_days_map=study_days_map,
        reserved_minutes_by_day=reserved_minutes_by_day,
        fixed_blocks=busy_blocks,
        allow_sprint_overflow=True,
    ))
    if schedule.status != "success":
        schedule = ScheduleResult("success", [], {"status": "success", "is_over_budget": True}, "over_budget")

    await _replace_generated_tasks(pool, user_id, today)
    await repository.insert_study_tasks(pool, schedule.task_dicts())
    await _set_coverage_warning(pool, subjects, schedule.coverage_warning)
    await repository.set_plan_dirty(pool, user_id, False)

    return {
        "status": "success",
        "tasks": schedule.task_dicts(),
        "coverageWarning": schedule.coverage_warning,
    }


async def _build_subject_schedule_locked(
    pool: asyncpg.Pool,
    user_id: str,
    subject_id: str,
    today: date,
    preferred_start_time: str | None = None,
) -> dict[str, Any]:
    await ensure_missed_tasks_marked(pool, user_id, today)
    profile = await repository.get_profile(pool, user_id)
    if not profile:
        return {"status": "error", "message": "Profile not found"}

    subjects = await repository.get_subjects(pool, user_id)
    subject = subjects.get(subject_id)
    if not subject:
        return {"status": "error", "message": "Subject not found"}

    topic_map = {subject_id: await repository.get_topics(pool, subject_id)}
    horizon = _subject_planning_horizon(today, subject)
    study_days_map = [_is_study_day(today + timedelta(days=offset), subject, profile) for offset in range(horizon)]
    daily_budget = max(0, int(subject.daily_goal_minutes or profile.daily_goal_minutes or settings.DEFAULT_DAILY_GOAL_MINUTES))
    start_hhmm = _parse_hhmm(preferred_start_time) if preferred_start_time else _preferred_start_time(profile)
    reserved_minutes_by_day, fixed_blocks = await _fixed_schedule_state(pool, user_id, subject_id, today, horizon, [subject], profile)
    reserved_minutes_by_day = _with_window_capacity_adjustments(
        today,
        horizon,
        [subject],
        profile,
        daily_budget,
        reserved_minutes_by_day,
    )

    # In a course-scoped rebuild, existing subjects are fixed calendar blocks.
    # New coverage may append after them; otherwise a full day in another subject makes this subject infeasible.
    schedule = build_schedule_from_inputs(ScheduleInput(
        user_id=user_id,
        today=today,
        profile=profile,
        subjects={subject_id: subject},
        topic_map=topic_map,
        horizon=horizon,
        daily_budget=daily_budget,
        start_hhmm=start_hhmm,
        study_days_map=study_days_map,
        reserved_minutes_by_day=reserved_minutes_by_day,
        fixed_blocks=fixed_blocks,
        allow_sprint_overflow=True,
    ))
    if schedule.status != "success":
        schedule = ScheduleResult("success", [], {"status": "success", "is_over_budget": True}, "over_budget")

    await _replace_generated_tasks(pool, user_id, today, subject_id=subject_id)
    await repository.insert_study_tasks(pool, schedule.task_dicts())
    await _set_coverage_warning(pool, [subject], schedule.coverage_warning)
    await repository.set_plan_dirty(pool, user_id, False)

    return {
        "status": "success",
        "tasks": schedule.task_dicts(),
        "coverageWarning": schedule.coverage_warning,
    }


async def _build_selected_subjects_schedule_locked(
    pool: asyncpg.Pool,
    user_id: str,
    subject_ids: Sequence[str],
    today: date,
) -> dict[str, Any]:
    await ensure_missed_tasks_marked(pool, user_id, today)
    profile = await repository.get_profile(pool, user_id)
    if not profile:
        return {"status": "error", "message": "Profile not found"}

    all_subjects = await repository.get_subjects(pool, user_id)
    selected_ids = set(subject_ids)
    subjects = {subject_id: subject for subject_id, subject in all_subjects.items() if subject_id in selected_ids}
    if not subjects:
        return {"status": "error", "message": "Subject not found"}

    topic_map = {
        subject_id: await repository.get_topics(pool, subject_id)
        for subject_id in subjects
    }
    horizon = _planning_horizon(today, subjects.values())
    study_days_map = [_any_subject_studies(today + timedelta(days=offset), subjects.values(), profile) for offset in range(horizon)]
    daily_budget = max(0, int(profile.daily_goal_minutes or settings.DEFAULT_DAILY_GOAL_MINUTES))
    start_hhmm = _preferred_start_time(profile)
    reserved_minutes_by_day, fixed_blocks = await _fixed_schedule_state_for_subjects(pool, user_id, selected_ids, today, horizon, subjects.values(), profile)
    reserved_minutes_by_day = _with_window_capacity_adjustments(
        today,
        horizon,
        subjects.values(),
        profile,
        daily_budget,
        reserved_minutes_by_day,
    )

    schedule = build_schedule_from_inputs(ScheduleInput(
        user_id=user_id,
        today=today,
        profile=profile,
        subjects=subjects,
        topic_map=topic_map,
        horizon=horizon,
        daily_budget=daily_budget,
        start_hhmm=start_hhmm,
        study_days_map=study_days_map,
        reserved_minutes_by_day=reserved_minutes_by_day,
        fixed_blocks=fixed_blocks,
        allow_sprint_overflow=True,
    ))
    if schedule.status != "success":
        schedule = ScheduleResult("success", [], {"status": "success", "is_over_budget": True}, "over_budget")

    await _replace_generated_tasks_for_subjects(pool, user_id, today, selected_ids)
    await repository.insert_study_tasks(pool, schedule.task_dicts())
    await _set_coverage_warning(pool, subjects, schedule.coverage_warning)
    await repository.set_plan_dirty(pool, user_id, False)

    return {
        "status": "success",
        "tasks": schedule.task_dicts(),
        "coverageWarning": schedule.coverage_warning,
    }

async def _replace_generated_tasks(pool: asyncpg.Pool, user_id: str, from_date: date, subject_id: str | None = None) -> None:
    subject_filter = "AND subject_id=$5" if subject_id else ""
    values = [user_id, from_date, list(GENERATED_TYPES), ["new", "preview"]]
    if subject_id:
        values.append(subject_id)
    async with pool.acquire() as conn:
        await conn.execute(
            f"""DELETE FROM study_tasks
               WHERE user_id=$1
                 AND scheduled_date >= $2
                 AND (
                   (status='ready' AND LOWER(type) = ANY($3::text[]))
                   OR LOWER(type) = ANY($4::text[])
                 )
                 {subject_filter}""",
            *values,
        )


async def _replace_generated_tasks_for_subjects(pool: asyncpg.Pool, user_id: str, from_date: date, subject_ids: set[str]) -> None:
    if not subject_ids:
        return
    async with pool.acquire() as conn:
        await conn.execute(
            """DELETE FROM study_tasks
               WHERE user_id=$1
                 AND scheduled_date >= $2
                 AND (
                   (status='ready' AND LOWER(type) = ANY($3::text[]))
                   OR LOWER(type) = ANY($4::text[])
                 )
                 AND subject_id = ANY($5::text[])""",
            user_id,
            from_date,
            list(GENERATED_TYPES),
            ["new", "preview"],
            list(subject_ids),
        )

async def _set_coverage_warning(pool: asyncpg.Pool, subjects: dict[str, Subject] | Sequence[Subject], warning: str | None) -> None:
    items = subjects.values() if isinstance(subjects, dict) else subjects
    for subject in items:
        await repository.update_subject(pool, subject.id, coverage_warning=warning)


def _solve_coverage_with_deadline_relaxation(
    pool_new: list[dict[str, Any]],
    daily_budget: int,
    horizon: int,
    effective_horizon: int,
    study_days_map: list[bool],
    reserved_minutes_by_day: dict[int, int],
) -> dict[str, Any]:
    solver_budget = max(
        daily_budget,
        max((int(item["cost_mins"]) for item in pool_new), default=settings.MIN_DAILY_TASK_MINUTES),
    )
    result = solve_coverage_pass(
        pool_new,
        solver_budget,
        effective_horizon,
        study_days_map,
        reserved_minutes_by_day,
    )
    if result.get("status") != "success":
        initial_result = result
        result = solve_coverage_pass(
            pool_new,
            solver_budget,
            effective_horizon,
            study_days_map,
            reserved_minutes_by_day,
            relax_deadlines=True,
        )
        if result.get("status") == "success":
            result["is_over_budget"] = True
            result["relaxed_deadlines"] = True
            result["cp_retry_reason"] = initial_result
    if result.get("status") == "success" and solver_budget > daily_budget:
        result["is_over_budget"] = True
    if result.get("status") == "success" and any(int(day_offset) >= horizon for day_offset in (result.get("schedule") or {})):
        result["is_over_budget"] = True
    return result


def _coverage_topic_pool(
    today: date,
    subjects: dict[str, Subject],
    topic_map: dict[str, list[Topic]],
    profile: UserProfile,
    effective_horizon: int,
    start_hhmm: tuple[int, int],
    fixed_blocks: Sequence[ScheduledBlock],
    ignore_study_days: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, CoverageTopicItem]]:
    pool_new: list[dict[str, Any]] = []
    by_item_id: dict[str, CoverageTopicItem] = {}
    for subject_id, subject in subjects.items():
        deadline_day = (subject.exam_date - today).days if subject.exam_date and subject.exam_date > today else None
        sprint_active = _active_behavior(subject, today) == "exam_sprint"
        subject_topics = topic_map.get(subject_id, [])
        in_semester = _subject_in_semester(today, subject_topics)
        for topic in _schedulable_topics(subject_topics):
            children = _topic_children(topic, subject_topics) if _is_chapter_parent_topic(topic) else []
            if topic.is_learned and (not children or _chapter_ready_for_topic_review(children)):
                continue
            if not _topic_schedulable_on_or_after(today, topic, in_semester):
                continue
            cost_mins = REVIEW_TASK_MINUTES
            if sprint_active:
                coverage_items = _sprint_coverage_items_for_topic(topic, subject_topics)
            else:
                coverage_items = _coverage_items_for_topic(today, topic, subject_topics, effective_horizon, in_semester)
            for coverage_item in coverage_items:
                item_id = coverage_item.id
                earliest_offset = coverage_item.earliest_offset
                by_item_id[item_id] = coverage_item
                pool_new.append({
                    "id": item_id,
                    "subject_id": subject_id,
                    "cost_mins": cost_mins,
                    "order_idx": topic.order_idx,
                    "subject_deadline_day": deadline_day,
                    "target_day_offset": earliest_offset,
                    "target_penalty_weight": 6,
                    "allowed_day_offsets": [
                        offset
                        for offset in range(effective_horizon)
                        if offset >= earliest_offset and (ignore_study_days or _is_study_day(today + timedelta(days=offset), subject, profile))
                        and _place_task_in_day(
                            today + timedelta(days=offset),
                            cost_mins,
                            subject,
                            profile,
                            start_hhmm,
                            fixed_blocks,
                            earliest_at=_topic_earliest_allowed_at(topic, today + timedelta(days=offset), in_semester, fixed_blocks, is_exam_sprint=sprint_active),
                        )
                    ],
                })
    return pool_new, by_item_id


def _build_coverage_blocks(
    user_id: str,
    today: date,
    subjects: dict[str, Subject],
    topic_map: dict[str, list[Topic]],
    profile: UserProfile,
    daily_budget: int,
    horizon: int,
    study_days_map: list[bool],
    start_hhmm: tuple[int, int],
    reserved_minutes_by_day: dict[int, int] | None = None,
    fixed_blocks: Sequence[ScheduledBlock] | None = None,
) -> tuple[list[ScheduledBlock], dict[str, Any]]:
    fixed_blocks = fixed_blocks or []
    by_subject_id = subjects
    sprint_planning = _has_exam_sprint(subjects.values(), today)
    effective_horizon = horizon if sprint_planning else max(horizon, horizon + CP_EXTENSION_DAYS)
    effective_study_days_map = list(study_days_map)
    if len(effective_study_days_map) < effective_horizon:
        effective_study_days_map.extend(
            _any_subject_studies(today + timedelta(days=offset), subjects.values(), profile)
            for offset in range(len(effective_study_days_map), effective_horizon)
        )
    effective_reserved_minutes_by_day = dict(reserved_minutes_by_day or {})
    pool_new, by_item_id = _coverage_topic_pool(
        today,
        subjects,
        topic_map,
        profile,
        effective_horizon,
        start_hhmm,
        fixed_blocks,
    )

    result = _solve_coverage_with_deadline_relaxation(
        pool_new,
        daily_budget,
        horizon,
        effective_horizon,
        effective_study_days_map,
        effective_reserved_minutes_by_day,
    )

    placement_fixed_blocks = fixed_blocks
    if result.get("status") != "success":
        initial_result = result
        # Run 2: schedule on any day of the week (ignore preferred study days) but still respect busy events
        pool_new, by_item_id = _coverage_topic_pool(
            today,
            subjects,
            topic_map,
            profile,
            effective_horizon,
            start_hhmm,
            fixed_blocks,
            ignore_study_days=True,
        )
        fallback_study_days_map = [True] * len(effective_study_days_map)
        result = _solve_coverage_with_deadline_relaxation(
            pool_new,
            daily_budget,
            horizon,
            effective_horizon,
            fallback_study_days_map,
            effective_reserved_minutes_by_day,
        )
        if result.get("status") == "success":
            result["is_over_budget"] = True
            result["relaxed_study_days"] = True
            result["cp_retry_reason"] = initial_result
    if result.get("status") != "success":
        # Fallback 3: Relax daily budget to find a feasible solution under high workload
        for multiplier in [2, 3, 5, 10]:
            relaxed_budget = daily_budget * multiplier
            result = _solve_coverage_with_deadline_relaxation(
                pool_new,
                relaxed_budget,
                horizon,
                effective_horizon,
                fallback_study_days_map,
                effective_reserved_minutes_by_day,
            )
            if result.get("status") == "success":
                result["is_over_budget"] = True
                result["relaxed_study_days"] = True
                result["relaxed_budget"] = True
                break
    if result.get("status") != "success":
        return [], result

    blocks: list[ScheduledBlock] = []
    for day_offset, day_plan in sorted((result.get("schedule") or {}).items()):
        target_day = today + timedelta(days=int(day_offset))
        for item_id in day_plan.get("new_topics", []):
            item = by_item_id.get(item_id)
            if not item:
                continue
            topic = item.topic
            subject = subjects.get(topic.subject_id)
            if not subject:
                continue
            in_semester = _subject_in_semester(today, topic_map.get(topic.subject_id, []))
            minutes = REVIEW_TASK_MINUTES
            sprint_active = bool(_active_behavior(subject, today) == "exam_sprint")
            placement = _place_task_in_day(
                target_day,
                minutes,
                subject,
                profile,
                start_hhmm,
                [*placement_fixed_blocks, *blocks],
                earliest_at=_topic_earliest_allowed_at(topic, target_day, in_semester, placement_fixed_blocks, is_exam_sprint=sprint_active),
            )
            if not placement:
                continue
            start_at, end_at = placement
            curr = target_day
            scope_info = _task_scope_for_topic(topic, topic_map.get(topic.subject_id, []), curr, item.scope_child_ids)
            partial = scope_info["partial"]
            task_scope = "partial_topic" if partial else "topic"
            task_type = "review"
            task_title = f"Review: {topic.title}"
            reason = _coverage_reason(topic, partial)
            sprint_active = bool(subject and _active_behavior(subject, curr) == "exam_sprint")
            if sprint_active:
                days_left = max(0, (subject.exam_date - curr).days) if subject and subject.exam_date else 0
                reason = f"Ôn thi tăng tốc ({days_left} ngày trước thi). Phủ lại nội dung trọng tâm trước kỳ thi."
            if scope_info["summary"]:
                reason = f"{reason} {scope_info['summary']}"

            blocks.append(ScheduledBlock(task=StudyTask(
                id=f"task-{curr.isoformat()}-{_task_id_key(str(item_id))}",
                subject_id=topic.subject_id,
                topic_id=topic.id,
                user_id=user_id,
                topic_title=topic.title,
                type=task_type,
                duration_minutes=minutes,
                reason=reason,
                scheduled_date=curr,
                status="ready",
                day=curr.strftime("%a"),
                title=task_title,
                start_at=start_at,
                end_at=end_at,
                priority="high" if topic.mastery < 0.5 else "medium",
                lesson_id=item.lesson_id,
                lesson_title=scope_info["summary"],
                learning_state=topic.learning_state,
                subtopic_id=None,
                parent_topic_id=topic.id if _is_chapter_parent_topic(topic) else topic.parent_topic_id,
                is_partial_topic=partial,
                scope=task_scope,
                earliest_allowed_at=_topic_earliest_allowed_at(topic, curr, in_semester, placement_fixed_blocks, is_exam_sprint=sprint_active),
            ), scope_child_ids=item.scope_child_ids))
    return blocks, result


def _build_review_blocks(
    user_id: str,
    today: date,
    subjects: dict[str, Subject],
    topic_map: dict[str, list[Topic]],
    profile: UserProfile,
    daily_budget: int,
    horizon: int,
    coverage_blocks: list[ScheduledBlock],
    start_hhmm: tuple[int, int],
    reserved_minutes_by_day: dict[int, int] | None = None,
    fixed_blocks: Sequence[ScheduledBlock] | None = None,
    allow_sprint_overflow: bool = False,
) -> list[ScheduledBlock]:
    scheduler = get_scheduler(profile.fsrs_custom_weights)
    priority_scheduler = PriorityScheduler()
    blocks: list[ScheduledBlock] = []
    scheduled_by_day: dict[date, set[str]] = {}
    used_minutes_by_day: dict[date, int] = {
        today + timedelta(days=offset): minutes
        for offset, minutes in (reserved_minutes_by_day or {}).items()
    }
    fixed_blocks = fixed_blocks or []
    generated_count_by_day: dict[date, int] = {}

    for block in fixed_blocks:
        block_key = _scheduled_block_scope_key(block)
        if block_key:
            scheduled_by_day.setdefault(block.task.scheduled_date, set()).add(block_key)

    for block in coverage_blocks:
        block_key = _scheduled_block_scope_key(block)
        if block_key:
            scheduled_by_day.setdefault(block.task.scheduled_date, set()).add(block_key)
        used_minutes_by_day[block.task.scheduled_date] = used_minutes_by_day.get(block.task.scheduled_date, 0) + block.task.duration_minutes
        generated_count_by_day[block.task.scheduled_date] = generated_count_by_day.get(block.task.scheduled_date, 0) + 1
    coverage_day_by_scope = {
        _scheduled_block_scope_key(block): block.task.scheduled_date
        for block in coverage_blocks
        if _scheduled_block_scope_key(block)
    }

    sim_topics = {
        subject_id: [topic.model_copy(deep=True) for topic in topics]
        for subject_id, topics in topic_map.items()
    }
    sim_topic_by_id = {
        topic.id: topic
        for topics in sim_topics.values()
        for topic in topics
    }
    coverage_blocks_by_day: dict[date, list[ScheduledBlock]] = {}
    for block in coverage_blocks:
        coverage_blocks_by_day.setdefault(block.task.scheduled_date, []).append(block)
    simulated_coverage_block_ids: set[str] = set()
    sprint_next_allowed_by_scope: dict[str, date] = {}
    for block in coverage_blocks:
        block_key = _scheduled_block_scope_key(block)
        subject = subjects.get(block.task.subject_id)
        topic = sim_topic_by_id.get(block.task.topic_id or "")
        if block_key and subject and topic and _active_behavior(subject, block.task.scheduled_date) == "exam_sprint":
            sprint_next_allowed_by_scope[block_key] = block.task.scheduled_date + timedelta(days=_sprint_spacing_days(topic.mastery))
    yesterday_scopes: set[str] = set()

    for offset in range(horizon):
        curr = today + timedelta(days=offset)
        for coverage_day in sorted(day for day in coverage_blocks_by_day if day < curr):
            for block in coverage_blocks_by_day[coverage_day]:
                if block.task.id in simulated_coverage_block_ids:
                    continue
                topic = sim_topic_by_id.get(block.task.topic_id or "")
                if topic:
                    _simulate_successful_task(topic, block.scope_child_ids, sim_topic_by_id, block.task.scheduled_date, scheduler)
                simulated_coverage_block_ids.add(block.task.id)

        if not _any_subject_studies(curr, subjects.values(), profile):
            yesterday_scopes = set()
            continue

        continuous_capacity = max(0, MAX_CONTINUOUS_REVIEW_BLOCKS_PER_DAY - generated_count_by_day.get(curr, 0))
        remaining = max(0, daily_budget - used_minutes_by_day.get(curr, 0))
        sprint_day_active = _has_exam_sprint(subjects.values(), curr)
        if remaining < settings.MIN_DAILY_TASK_MINUTES and allow_sprint_overflow and sprint_day_active:
            remaining = _sprint_review_overflow_budget(subjects.values(), daily_budget, curr)
        if continuous_capacity <= 0 and not (allow_sprint_overflow and sprint_day_active):
            yesterday_scopes = scheduled_by_day.get(curr, set())
            continue
        if remaining < settings.MIN_DAILY_TASK_MINUTES:
            yesterday_scopes = scheduled_by_day.get(curr, set())
            continue

        candidates = []
        for subject_id, subject in subjects.items():
            if not _is_study_day(curr, subject, profile):
                continue
            exam_date = subject.exam_date or (curr + timedelta(days=90))
            sprint_active = _active_behavior(subject, curr) == "exam_sprint"
            in_semester = _subject_in_semester(curr, sim_topics.get(subject_id, []))
            for topic in _review_candidate_topics(sim_topics.get(subject_id, [])):
                if not sprint_active and topic.learning_state == "future" and not topic.practice_allowed:
                    continue
                if not sprint_active and curr < _earliest_normal_day(today, topic, in_semester):
                    continue
                if not sprint_active and not _topic_available_for_review(topic, curr, in_semester):
                    continue
                child_scope_ids = _review_scope_child_ids(topic, sim_topics.get(topic.subject_id, []))
                scope_key = _scope_schedule_key(topic, child_scope_ids)
                if sprint_active and sprint_next_allowed_by_scope.get(scope_key, curr) > curr:
                    continue
                coverage_day = coverage_day_by_scope.get(scope_key)
                if coverage_day and curr <= coverage_day:
                    continue
                if (not sprint_active and topic.awaiting_diagnostic) or scope_key in scheduled_by_day.get(curr, set()):
                    continue
                if not sprint_active and topic.fsrs_due_date and topic.fsrs_due_date > curr:
                    continue
                due = bool(topic.fsrs_due_date and topic.fsrs_due_date <= curr)
                weak = topic.mastery < 0.70
                if not sprint_active and (not topic.is_learned or (not due and not weak)):
                    continue
                if sprint_active:
                    score_info = _sprint_score_info(topic, subject, curr, exam_date, scheduler, child_scope_ids)
                else:
                    score_info = priority_scheduler.urgency(topic, curr, exam_date, scheduler, subject.is_priority)
                candidates.append((topic, subject, score_info, child_scope_ids, scope_key))

        candidates.sort(key=lambda item: item[2]["urgency"], reverse=True)
        preferred = [item for item in candidates if item[4] not in yesterday_scopes]
        pool = preferred or candidates
        max_blocks = _sprint_review_block_capacity(remaining) if allow_sprint_overflow and sprint_day_active else continuous_capacity
        max_blocks = min(max_blocks, remaining // REVIEW_TASK_MINUTES)
        allocations = [(item, REVIEW_TASK_MINUTES) for item in pool[:max_blocks] if remaining >= REVIEW_TASK_MINUTES]

        today_scopes = scheduled_by_day.setdefault(curr, set())
        for (topic, subject, scores, child_scope_ids, scope_key), minutes in allocations:
            if scope_key in today_scopes:
                continue
            in_semester = _subject_in_semester(curr, sim_topics.get(topic.subject_id, []))
            is_sprint_task = bool(subject and _active_behavior(subject, curr) == "exam_sprint")
            all_blocks = [*fixed_blocks, *coverage_blocks, *blocks]
            placement = _place_task_in_day(
                curr,
                minutes,
                subject,
                profile,
                start_hhmm,
                all_blocks,
                earliest_at=_topic_earliest_allowed_at(topic, curr, in_semester, all_blocks, is_exam_sprint=is_sprint_task),
            )
            if not placement:
                continue
            start_at, end_at = placement
            today_scopes.add(scope_key)
            is_sprint_task = _active_behavior(subject, curr) == "exam_sprint"
            scope_info = _task_scope_for_topic(
                topic,
                sim_topics.get(topic.subject_id, []),
                curr,
                child_scope_ids,
                sprint=is_sprint_task,
            )
            partial = scope_info["partial"] or _is_partial_topic_task(topic, sim_topics.get(topic.subject_id, []))
            task_scope = "partial_topic" if partial else "topic"
            reason = (
                f"{_review_reason_prefix(topic, partial)} "
                f"Urgency {scores['urgency']:.2f}: forgetting {scores['forgetting_risk'] * 100:.0f}%, "
                f"mastery {topic.mastery * 100:.0f}%."
            )
            if is_sprint_task:
                days_left = max(0, (subject.exam_date - curr).days) if subject.exam_date else 0
                reason = (
                    f"Ôn thi tăng tốc ({days_left} ngày trước thi). "
                    f"Urgency {scores['urgency']:.2f}: retention gap {scores.get('retention_gap', 0.0) * 100:.0f}%, "
                    f"forgetting {scores['forgetting_risk'] * 100:.0f}%, mastery {topic.mastery * 100:.0f}%."
                )
            if scope_info["summary"]:
                reason = f"{reason} {scope_info['summary']}"
            blocks.append(ScheduledBlock(task=StudyTask(
                id=f"task-{curr.isoformat()}-{topic.id}",
                subject_id=topic.subject_id,
                topic_id=topic.id,
                user_id=user_id,
                topic_title=topic.title,
                type="review",
                duration_minutes=minutes,
                reason=reason,
                scheduled_date=curr,
                status="ready",
                day=curr.strftime("%a"),
                title=f"Review: {topic.title}",
                start_at=start_at,
                end_at=end_at,
                priority="high" if scores["urgency"] >= 0.8 or topic.mastery < 0.5 else "medium",
                lesson_id=topic.lesson_id,
                lesson_title=scope_info["summary"],
                learning_state=topic.learning_state,
                subtopic_id=None if _is_chapter_parent_topic(topic) else topic.id,
                parent_topic_id=topic.id if _is_chapter_parent_topic(topic) else topic.parent_topic_id,
                is_partial_topic=partial,
                scope=task_scope,
                earliest_allowed_at=_topic_earliest_allowed_at(topic, curr, in_semester, all_blocks, is_exam_sprint=is_sprint_task),
            ), scope_child_ids=child_scope_ids))
            sprint_spacing_days = _sprint_spacing_days(topic.mastery) if is_sprint_task else MIN_CONTINUOUS_REVIEW_SPACING_DAYS
            _simulate_successful_task(topic, child_scope_ids, sim_topic_by_id, curr, scheduler, sprint=is_sprint_task)
            if is_sprint_task:
                sprint_next_allowed_by_scope[scope_key] = curr + timedelta(days=sprint_spacing_days)
            generated_count_by_day[curr] = generated_count_by_day.get(curr, 0) + 1
            remaining -= minutes
        yesterday_scopes = today_scopes
    return blocks


def _is_study_day(day: date, subject: Subject, profile: UserProfile) -> bool:
    day_name = day.strftime("%a")
    if subject.availability_windows:
        return bool(_subject_windows_for_day(day, subject))
    allowed_days = subject.days_available or profile.study_days
    return not allowed_days or day_name in allowed_days


def _any_subject_studies(day: date, subjects: Sequence[Subject], profile: UserProfile) -> bool:
    return any(_is_study_day(day, subject, profile) for subject in subjects)

def _has_exam_sprint(subjects: Sequence[Subject], today: date) -> bool:
    return any(_active_behavior(subject, today) == "exam_sprint" for subject in subjects)


def _active_behavior(subject: Subject, today: date) -> str:
    if subject.exam_date and 0 <= (subject.exam_date - today).days <= 14:
        return "exam_sprint"
    return "continuous"

def _sprint_review_overflow_budget(subjects: Sequence[Subject], fallback_budget: int, today: date) -> int:
    sprint_budgets = [
        int(subject.daily_goal_minutes or 0)
        for subject in subjects
        if _active_behavior(subject, today) == "exam_sprint"
    ]
    budget = max([fallback_budget, settings.DEFAULT_DAILY_GOAL_MINUTES, *sprint_budgets])
    return max(settings.MIN_DAILY_TASK_MINUTES, min(SPRINT_REVIEW_BUDGET_CAP_MINUTES, budget))

def _sprint_review_block_capacity(minutes: int) -> int:
    return max(0, minutes // REVIEW_TASK_MINUTES)


def _sprint_score_info(
    topic: Topic,
    subject: Subject,
    curr: date,
    exam_date: date,
    scheduler: Any,
    scope_child_ids: Sequence[str],
) -> dict[str, float]:
    retention = FSRSScheduler.get_retention(topic, curr, scheduler)
    retention_gap = max(0.0, settings.DESIRED_RETENTION_SPRINT - retention)
    mastery_gap = max(0.0, 1.0 - float(topic.mastery or 0.0))
    overdue_boost = 0.25 if topic.fsrs_due_date and topic.fsrs_due_date <= curr else 0.0
    days_left = max(0, (exam_date - curr).days)
    exam_proximity_boost = max(0.0, (14 - min(14, days_left)) / 14)
    weak_subtopic_boost = 0.20 if scope_child_ids and topic.mastery < 0.50 else 0.0
    unlearned_boost = 0.20 if not topic.is_learned else 0.0
    priority_boost = 0.15 if subject.is_priority else 0.0
    final_sweep_boost = 0.15 if days_left <= 2 and not scope_child_ids else 0.0
    urgency = (
        retention_gap
        + mastery_gap
        + overdue_boost
        + exam_proximity_boost
        + weak_subtopic_boost
        + unlearned_boost
        + priority_boost
        + final_sweep_boost
    )
    return {
        "urgency": urgency,
        "forgetting_risk": 1.0 - retention,
        "weakness": mastery_gap,
        "retention_gap": retention_gap,
    }


async def _fixed_schedule_state(
    pool: asyncpg.Pool,
    user_id: str,
    rebuilding_subject_id: str,
    today: date,
    horizon: int,
    rebuilding_subjects: Sequence[Subject],
    profile: UserProfile,
) -> tuple[dict[int, int], list[ScheduledBlock]]:
    tasks = await repository.get_weekly_tasks_all_subjects(pool, user_id, today)
    end_date = today + timedelta(days=horizon)
    reserved_minutes_by_day: dict[int, int] = {}
    fixed_blocks: list[ScheduledBlock] = []

    for task in tasks:
        if task.scheduled_date < today or task.scheduled_date >= end_date:
            continue
        if task.status not in ACTIVE_TASK_STATUSES:
            continue
        if task.subject_id == rebuilding_subject_id and task.status == "ready" and task.type.lower() in LEGACY_GENERATED_TYPES:
            continue

        offset = (task.scheduled_date - today).days
        reserved_minutes_by_day[offset] = reserved_minutes_by_day.get(offset, 0) + max(0, int(task.duration_minutes or 0))
        fixed_blocks.append(ScheduledBlock(task=task))

    busy_event_blocks = await _busy_event_blocks(pool, user_id, today, horizon)
    class_blocks = await _class_meeting_blocks(pool, user_id, today, horizon)
    busy_blocks = [*busy_event_blocks, *class_blocks]
    busy_reserved = _busy_reserved_minutes_by_day(today, horizon, busy_blocks, rebuilding_subjects, profile)
    for offset, minutes in busy_reserved.items():
        reserved_minutes_by_day[offset] = reserved_minutes_by_day.get(offset, 0) + minutes
    for block in busy_blocks:
        fixed_blocks.append(block)

    return reserved_minutes_by_day, fixed_blocks


async def _fixed_schedule_state_for_subjects(
    pool: asyncpg.Pool,
    user_id: str,
    rebuilding_subject_ids: set[str],
    today: date,
    horizon: int,
    rebuilding_subjects: Sequence[Subject],
    profile: UserProfile,
) -> tuple[dict[int, int], list[ScheduledBlock]]:
    tasks = await repository.get_weekly_tasks_all_subjects(pool, user_id, today)
    end_date = today + timedelta(days=horizon)
    reserved_minutes_by_day: dict[int, int] = {}
    fixed_blocks: list[ScheduledBlock] = []

    for task in tasks:
        if task.scheduled_date < today or task.scheduled_date >= end_date:
            continue
        if task.status not in ACTIVE_TASK_STATUSES:
            continue
        if task.subject_id in rebuilding_subject_ids and task.status == "ready" and task.type.lower() in LEGACY_GENERATED_TYPES:
            continue

        offset = (task.scheduled_date - today).days
        reserved_minutes_by_day[offset] = reserved_minutes_by_day.get(offset, 0) + max(0, int(task.duration_minutes or 0))
        fixed_blocks.append(ScheduledBlock(task=task))

    busy_event_blocks = await _busy_event_blocks(pool, user_id, today, horizon)
    class_blocks = await _class_meeting_blocks(pool, user_id, today, horizon)
    busy_blocks = [*busy_event_blocks, *class_blocks]
    busy_reserved = _busy_reserved_minutes_by_day(today, horizon, busy_blocks, rebuilding_subjects, profile)
    for offset, minutes in busy_reserved.items():
        reserved_minutes_by_day[offset] = reserved_minutes_by_day.get(offset, 0) + minutes
    for block in busy_blocks:
        fixed_blocks.append(block)

    return reserved_minutes_by_day, fixed_blocks

async def _busy_event_blocks(pool: asyncpg.Pool, user_id: str, today: date, horizon: int) -> list[ScheduledBlock]:
    await repository.ensure_busy_events_table(pool)
    start = datetime.combine(today, time.min, tzinfo=APP_TZ)
    end = datetime.combine(today + timedelta(days=horizon), time.min, tzinfo=APP_TZ)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT * FROM busy_events
               WHERE user_id=$1 AND end_at >= $2 AND start_at < $3
               ORDER BY start_at, created_at""",
            user_id,
            start,
            end,
        )

    blocks: list[ScheduledBlock] = []
    for row in rows:
        start_at = row["start_at"].astimezone(APP_TZ)
        end_at = row["end_at"].astimezone(APP_TZ)
        minutes = max(1, round((end_at - start_at).total_seconds() / 60))
        blocks.append(ScheduledBlock(task=StudyTask(
            id=row["id"],
            subject_id="__busy__",
            topic_id=None,
            user_id=user_id,
            topic_title=row["title"],
            type="busy",
            duration_minutes=minutes,
            reason=row["reason"] or "Unavailable time.",
            scheduled_date=start_at.date(),
            status="busy",
            day=start_at.strftime("%a"),
            title=row["title"],
            start_at=start_at,
            end_at=end_at,
            priority="high",
        )))
    return blocks


async def _class_meeting_blocks(pool: asyncpg.Pool, user_id: str, today: date, horizon: int) -> list[ScheduledBlock]:
    end_date = today + timedelta(days=horizon)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT sl.id AS lesson_id, sl.subject_id, sl.title, sl.starts_on, sy.parsed_json
               FROM syllabus_lessons sl
               JOIN course_syllabi sy ON sy.id=sl.syllabus_id AND sy.user_id=$1
               WHERE sl.starts_on >= $2
                 AND sl.starts_on < $3
               ORDER BY sl.starts_on, sl.order_idx""",
            user_id,
            today,
            end_date,
        )
    return _class_meeting_blocks_from_rows(user_id, rows)


def _class_meeting_blocks_from_rows(user_id: str, rows: Sequence[Any]) -> list[ScheduledBlock]:
    blocks: list[ScheduledBlock] = []
    seen: set[tuple[str, date, int, int]] = set()
    for row in rows:
        starts_on = _record_get(row, "starts_on")
        if not isinstance(starts_on, date):
            continue
        calendar = _json_object(_record_get(row, "parsed_json")).get("calendar") or {}
        meetings = calendar.get("classMeetings") if isinstance(calendar, dict) else None
        if not isinstance(meetings, list):
            continue
        for meeting in meetings:
            if not isinstance(meeting, dict) or meeting.get("day") != starts_on.strftime("%a"):
                continue
            start_minute = _minutes_from_hhmm(meeting.get("start"))
            end_minute = _minutes_from_hhmm(meeting.get("end"))
            if start_minute is None or end_minute is None or end_minute <= start_minute:
                continue
            subject_id = str(_record_get(row, "subject_id") or "__class__")
            key = (subject_id, starts_on, start_minute, end_minute)
            if key in seen:
                continue
            seen.add(key)
            start_at = _datetime_at_minutes(starts_on, start_minute)
            end_at = _datetime_at_minutes(starts_on, end_minute)
            lesson_title = str(_record_get(row, "title") or "Class meeting")
            blocks.append(ScheduledBlock(task=StudyTask(
                id=f"class-{subject_id}-{starts_on.isoformat()}-{start_minute}-{end_minute}",
                subject_id=subject_id,
                topic_id=None,
                user_id=user_id,
                topic_title=lesson_title,
                type="busy",
                duration_minutes=max(1, end_minute - start_minute),
                reason="Class meeting from syllabus.",
                scheduled_date=starts_on,
                status="busy",
                day=starts_on.strftime("%a"),
                title=f"Class: {lesson_title}",
                start_at=start_at,
                end_at=end_at,
                priority="high",
            )))
    return blocks


def _record_get(row: Any, key: str, default: Any = None) -> Any:
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return default


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            data = json.loads(value)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def _is_class_meeting_block(block: ScheduledBlock) -> bool:
    task = block.task
    return str(task.id or "").startswith("class-") and task.reason == "Class meeting from syllabus."


def _reserved_minutes_by_day(today: date, horizon: int, blocks: Sequence[ScheduledBlock]) -> dict[int, int]:
    reserved: dict[int, int] = {}
    end_date = today + timedelta(days=horizon)
    for block in blocks:
        task = block.task
        if task.scheduled_date < today or task.scheduled_date >= end_date:
            continue
        offset = (task.scheduled_date - today).days
        reserved[offset] = reserved.get(offset, 0) + max(0, int(task.duration_minutes or 0))
    return reserved

def _busy_reserved_minutes_by_day(
    today: date,
    horizon: int,
    busy_blocks: Sequence[ScheduledBlock],
    subjects: Sequence[Subject],
    profile: UserProfile,
) -> dict[int, int]:
    reserved: dict[int, int] = {}
    end_date = today + timedelta(days=horizon)
    subjects_with_windows = [subject for subject in subjects if subject.availability_windows]
    if not subjects_with_windows:
        return reserved

    for block in busy_blocks:
        task = block.task
        if task.scheduled_date < today or task.scheduled_date >= end_date or not task.start_at or not task.end_at:
            continue
        windows = _study_window_intervals_for_day(task.scheduled_date, subjects_with_windows, profile)
        if not windows:
            continue
        offset = (task.scheduled_date - today).days
        overlap = sum(
            max(0, round((min(task.end_at, end_at) - max(task.start_at, start_at)).total_seconds() / 60))
            for start_at, end_at in windows
            if min(task.end_at, end_at) > max(task.start_at, start_at)
        )
        if overlap:
            reserved[offset] = reserved.get(offset, 0) + overlap
    return reserved

def _study_window_intervals_for_day(day: date, subjects: Sequence[Subject], profile: UserProfile) -> list[tuple[datetime, datetime]]:
    intervals: list[tuple[datetime, datetime]] = []
    for subject in subjects:
        if not _is_study_day(day, subject, profile):
            continue
        intervals.extend(
            (_datetime_at_minutes(day, start), _datetime_at_minutes(day, end))
            for start, end in _subject_windows_for_day(day, subject)
        )
    if not intervals:
        return []
    intervals.sort(key=lambda item: item[0])
    merged: list[tuple[datetime, datetime]] = []
    for start_at, end_at in intervals:
        if not merged or start_at > merged[-1][1]:
            merged.append((start_at, end_at))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end_at))
    return merged


def _with_window_capacity_adjustments(
    today: date,
    horizon: int,
    subjects: Sequence[Subject],
    profile: UserProfile,
    daily_budget: int,
    reserved: dict[int, int],
) -> dict[int, int]:
    adjusted = dict(reserved)
    if daily_budget <= 0:
        return adjusted
    for offset in range(horizon):
        curr = today + timedelta(days=offset)
        window_totals = [
            _subject_window_minutes(curr, subject)
            for subject in subjects
            if subject.availability_windows and _is_study_day(curr, subject, profile)
        ]
        if not window_totals:
            continue
        adjusted[offset] = adjusted.get(offset, 0) + max(0, daily_budget - max(window_totals))
    return adjusted

def _subject_window_minutes(day: date, subject: Subject) -> int:
    return sum(max(0, end - start) for start, end in _subject_windows_for_day(day, subject))

def _subject_windows_for_day(day: date, subject: Subject) -> list[tuple[int, int]]:
    weekday = day.strftime("%a")
    windows: list[tuple[int, int]] = []
    for item in subject.availability_windows or []:
        if not isinstance(item, dict) or item.get("day") != weekday:
            continue
        start = _minutes_from_hhmm(item.get("start"))
        end = _minutes_from_hhmm(item.get("end"))
        if start is None or end is None or end <= start:
            continue
        windows.append((start, end))
    return sorted(windows)

def _minutes_from_hhmm(value: Any) -> int | None:
    try:
        hour_text, minute_text = str(value).split(":")[:2]
        hour = int(hour_text)
        minute = int(minute_text)
    except Exception:
        return None
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return None
    return hour * 60 + minute

def _datetime_at_minutes(day: date, minutes: int) -> datetime:
    return datetime.combine(day, time(minutes // 60, minutes % 60), tzinfo=APP_TZ)

def _place_task_in_day(
    day: date,
    minutes: int,
    subject: Subject,
    profile: UserProfile,
    start_hhmm: tuple[int, int],
    blocks: Sequence[ScheduledBlock],
    earliest_at: datetime | None = None,
) -> tuple[datetime, datetime] | None:
    if earliest_at and earliest_at > datetime.combine(day, time.max, tzinfo=APP_TZ):
        return None

    if not subject.availability_windows:
        start = _next_cursor(day, start_hhmm, blocks)
        if earliest_at and start < earliest_at:
            start = earliest_at
        return start, start + timedelta(minutes=minutes)

    windows = _subject_windows_for_day(day, subject)
    if not windows:
        return None

    occupied = sorted(
        (
            (block.task.start_at, block.task.end_at)
            for block in blocks
            if block.task.scheduled_date == day and block.task.start_at and block.task.end_at
        ),
        key=lambda item: item[0],
    )
    duration = timedelta(minutes=minutes)
    for start_minute, end_minute in windows:
        window_start = _datetime_at_minutes(day, start_minute)
        if earliest_at and earliest_at.date() == day:
            window_start = max(window_start, earliest_at)
        window_end = _datetime_at_minutes(day, end_minute)
        candidate = window_start
        for busy_start, busy_end in occupied:
            if busy_end <= candidate or busy_start >= window_end:
                continue
            if candidate + duration <= busy_start:
                break
            candidate = max(candidate, busy_end)
        if candidate + duration <= window_end:
            return candidate, candidate + duration
    return None


def _subject_planning_horizon(today: date, subject: Subject) -> int:
    if subject.exam_date and subject.exam_date > today:
        return max(1, (subject.exam_date - today).days)
    return 14


def _planning_horizon(today: date, subjects: Sequence[Subject]) -> int:
    future_exam_offsets = [
        (subject.exam_date - today).days
        for subject in subjects
        if subject.exam_date and subject.exam_date > today
    ]
    if not future_exam_offsets:
        return 14
    return max(1, min(future_exam_offsets))


def _preferred_start_time(profile: UserProfile) -> tuple[int, int]:
    window = profile.study_window or {}
    return _parse_hhmm(str(window.get("start") or "18:00"))


def _parse_hhmm(value: str) -> tuple[int, int]:
    try:
        hour_text, minute_text = f"{value}:00".split(":")[:2]
        return min(22, max(7, int(hour_text))), min(59, max(0, int(minute_text)))
    except Exception:
        return 18, 0


def _day_start(day: date, hhmm: tuple[int, int]) -> datetime:
    return datetime.combine(day, time(hhmm[0], hhmm[1]), tzinfo=APP_TZ)


def _next_cursor(day: date, hhmm: tuple[int, int], blocks: Sequence[ScheduledBlock]) -> datetime:
    ends = [block.task.end_at for block in blocks if block.task.scheduled_date == day and block.task.end_at]
    return max([_day_start(day, hhmm), *ends])


def _cost_from_mastery(mastery: float) -> int:
    return max(10, min(30, 15 + round((1 - mastery) * 15)))


def _schedulable_topics(topics: Sequence[Topic]) -> list[Topic]:
    canonical = [topic for topic in topics if _is_canonical_syllabus_topic(topic)]
    chapter_parents = [topic for topic in canonical if _is_chapter_syllabus_topic(topic) and not topic.is_subtopic]
    if chapter_parents:
        return chapter_parents
    return canonical or list(topics)

def _is_canonical_syllabus_topic(topic: Topic) -> bool:
    return str(topic.id or "").startswith(f"topic-{topic.subject_id}-syllabus-") or _is_chapter_syllabus_topic(topic)

def _is_chapter_syllabus_topic(topic: Topic) -> bool:
    return str(topic.id or "").startswith(f"topic-{topic.subject_id}-chapter-")

def _is_chapter_parent_topic(topic: Topic) -> bool:
    return _is_chapter_syllabus_topic(topic) and not topic.is_subtopic

def _chapter_ready_for_topic_review(children: Sequence[Topic]) -> bool:
    if not children:
        return False
    avg_mastery = sum(child.mastery for child in children) / len(children)
    avg_confidence = sum(float(child.mastery_confidence or 0.0) for child in children) / len(children)
    return (
        avg_mastery >= TOPIC_REVIEW_MASTERY_THRESHOLD
        and avg_confidence >= 0.55
        and all(child.is_learned for child in children)
    )

def _coverage_items_for_topic(
    today: date,
    topic: Topic,
    topics: Sequence[Topic],
    effective_horizon: int,
    subject_in_semester: bool,
) -> list[CoverageTopicItem]:
    if not _is_chapter_parent_topic(topic):
        earliest_offset = _earliest_normal_day_offset(today, topic, subject_in_semester)
        return [CoverageTopicItem(topic.id, topic, earliest_offset, topic.lesson_id)] if earliest_offset < effective_horizon else []

    children = _topic_children(topic, topics)
    if not children:
        earliest_offset = _earliest_normal_day_offset(today, topic, subject_in_semester)
        return [CoverageTopicItem(topic.id, topic, earliest_offset, topic.lesson_id)] if earliest_offset < effective_horizon else []

    groups: dict[tuple[date, str], list[Topic]] = {}
    for child in children:
        if child.mastery >= TOPIC_REVIEW_MASTERY_THRESHOLD and child.is_learned:
            continue
        earliest = _earliest_normal_day(today, child, subject_in_semester)
        if earliest == date.max:
            continue
        offset = max(0, (earliest - today).days)
        if offset >= effective_horizon:
            continue
        group_key = (earliest, child.lesson_id or child.id)
        groups.setdefault(group_key, []).append(child)

    items: list[CoverageTopicItem] = []
    for (earliest, group_id), group_children in sorted(groups.items(), key=lambda item: (item[0][0], min(child.order_idx for child in item[1]))):
        offset = max(0, (earliest - today).days)
        child_ids = tuple(child.id for child in sorted(group_children, key=lambda item: (item.order_idx, item.title)))
        item_id = f"{topic.id}::lesson::{_task_id_key(group_id)}"
        items.append(CoverageTopicItem(item_id, topic, offset, str(group_id), child_ids))
    return items


def _sprint_coverage_items_for_topic(topic: Topic, topics: Sequence[Topic]) -> list[CoverageTopicItem]:
    if not _is_chapter_parent_topic(topic):
        return [CoverageTopicItem(topic.id, topic, 0, topic.lesson_id)]
    children = [
        child
        for child in _topic_children(topic, topics)
        if not (child.mastery >= TOPIC_REVIEW_MASTERY_THRESHOLD and child.is_learned)
    ]
    if not children:
        return [CoverageTopicItem(topic.id, topic, 0, topic.lesson_id)]
    grouped: dict[str, list[Topic]] = {}
    for child in children:
        grouped.setdefault(child.lesson_id or child.id, []).append(child)
    items: list[CoverageTopicItem] = []
    for group_id, group_children in sorted(grouped.items(), key=lambda item: min(child.order_idx for child in item[1])):
        child_ids = tuple(child.id for child in sorted(group_children, key=lambda item: (item.order_idx, item.title)))
        item_id = f"{topic.id}::sprint::{_task_id_key(group_id)}"
        items.append(CoverageTopicItem(item_id, topic, 0, str(group_id), child_ids))
    return items


def _topic_children(topic: Topic, topics: Sequence[Topic]) -> list[Topic]:
    return sorted(
        [candidate for candidate in topics if candidate.parent_topic_id == topic.id and candidate.is_subtopic],
        key=lambda item: (item.order_idx, item.title),
    )

def _task_scope_for_topic(
    topic: Topic,
    topics: Sequence[Topic],
    day: date,
    scope_child_ids: Sequence[str] | None = None,
    sprint: bool = False,
) -> dict[str, Any]:
    children = _topic_children(topic, topics)
    if not children:
        return {"partial": False, "summary": ""}
    if scope_child_ids:
        scope_set = set(scope_child_ids)
        available = [child for child in children if child.id in scope_set]
    else:
        available = [child for child in children if _subtopic_available_on(child, day)]
    if not available:
        return {"partial": True, "summary": "Phạm vi: chưa có mục con đã học trên lớp."}
    full = len(available) >= len(children)
    titles = "; ".join(child.title for child in available)
    if full:
        return {"partial": False, "summary": f"Cả topic: {titles}"}
    return {"partial": True, "summary": f"Phạm vi đã học: {titles}"}

def _subtopic_available_on(topic: Topic, day: date) -> bool:
    if topic.lesson_starts_on:
        return topic.lesson_starts_on <= day
    return True

def _review_candidate_topics(topics: Sequence[Topic]) -> list[Topic]:
    result: list[Topic] = []
    for topic in _schedulable_topics(topics):
        if not _is_chapter_parent_topic(topic):
            result.append(topic)
            continue
        children = _topic_children(topic, topics)
        if children and _chapter_ready_for_topic_review(children):
            topic.mastery = sum(child.mastery for child in children) / len(children)
            topic.is_learned = True
            topic.awaiting_diagnostic = False
            topic.practice_allowed = True
            due_dates = [child.fsrs_due_date for child in children if child.fsrs_due_date]
            if due_dates:
                topic.fsrs_due_date = min(due_dates)
            result.append(topic)
            continue
        result.extend(_lesson_review_topics(topic, children))
    return result

def _lesson_review_topics(parent: Topic, children: Sequence[Topic]) -> list[Topic]:
    grouped: dict[str, list[Topic]] = {}
    for child in children:
        if child.mastery >= TOPIC_REVIEW_MASTERY_THRESHOLD and child.is_learned:
            continue
        grouped.setdefault(child.lesson_id or child.id, []).append(child)
    items: list[Topic] = []
    for lesson_children in grouped.values():
        if not lesson_children:
            continue
        clone = parent.model_copy(deep=True)
        clone.mastery = sum(child.mastery for child in lesson_children) / len(lesson_children)
        clone.is_learned = any(child.is_learned for child in lesson_children)
        clone.awaiting_diagnostic = all(child.awaiting_diagnostic for child in lesson_children)
        clone.practice_allowed = any(child.practice_allowed or child.is_learned for child in lesson_children)
        clone.lesson_id = lesson_children[0].lesson_id
        due_dates = [child.fsrs_due_date for child in lesson_children if child.fsrs_due_date]
        if due_dates:
            clone.fsrs_due_date = min(due_dates)
        items.append(clone)
    return items

def _review_scope_child_ids(topic: Topic, topics: Sequence[Topic]) -> tuple[str, ...]:
    if not _is_chapter_parent_topic(topic):
        return ()
    children = _topic_children(topic, topics)
    if not children:
        return ()
    if _chapter_ready_for_topic_review(children):
        return tuple(child.id for child in children)
    return tuple(child.id for child in children if child.lesson_id == topic.lesson_id)

def _scope_schedule_key(topic: Topic, scope_child_ids: Sequence[str] | None = None) -> str:
    if scope_child_ids:
        return f"children:{topic.id}:{'|'.join(sorted(scope_child_ids))}"
    return f"topic:{topic.id}"

def _scheduled_block_scope_key(block: ScheduledBlock) -> str | None:
    topic_id = block.task.topic_id
    if not topic_id:
        return None
    if block.scope_child_ids:
        return f"children:{topic_id}:{'|'.join(sorted(block.scope_child_ids))}"
    return f"topic:{topic_id}"

def _task_id_key(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in value)[:160]

def _topic_parent_key(topic: Topic) -> str:
    return topic.parent_topic_id or topic.id

def _is_partial_topic_task(topic: Topic, topics: Sequence[Topic]) -> bool:
    if topic.learning_state == "future":
        return False
    parent_key = _topic_parent_key(topic)
    siblings = [candidate for candidate in topics if _topic_parent_key(candidate) == parent_key]
    return any(candidate.learning_state == "future" and not candidate.practice_allowed for candidate in siblings)

def _topic_earliest_allowed_at(
    topic: Topic,
    fallback_day: date,
    subject_in_semester: bool,
    blocks: Sequence[ScheduledBlock],
    is_exam_sprint: bool = False,
) -> datetime:
    earliest_day = _earliest_normal_day(fallback_day, topic, subject_in_semester, is_exam_sprint)
    if earliest_day == date.max:
        return datetime.max.replace(tzinfo=APP_TZ)
    earliest_at = datetime.combine(earliest_day, time.min, tzinfo=APP_TZ)
    if topic.lesson_starts_on == fallback_day:
        class_ends = [
            block.task.end_at
            for block in blocks
            if _is_class_meeting_block(block)
            and block.task.subject_id == topic.subject_id
            and block.task.scheduled_date == fallback_day
            and block.task.end_at
        ]
        if class_ends:
            earliest_at = max(earliest_at, max(class_ends))
    return earliest_at

def _earliest_normal_day(today: date, topic: Topic, subject_in_semester: bool = False, is_exam_sprint: bool = False) -> date:
    if is_exam_sprint:
        return today
    if topic.learning_state == "future":
        if topic.lesson_starts_on:
            return max(today, topic.lesson_starts_on)
        return today
    if topic.learning_state in {"current", "taught"}:
        if subject_in_semester:
            return today
        if not topic.lesson_starts_on:
            return today
        return max(today, topic.lesson_starts_on)
    return today

def _earliest_normal_day_offset(today: date, topic: Topic, subject_in_semester: bool = False) -> int:
    earliest = _earliest_normal_day(today, topic, subject_in_semester)
    if earliest == date.max:
        return 10**9
    return max(0, (earliest - today).days)

def _topic_schedulable_on_or_after(today: date, topic: Topic, subject_in_semester: bool = False) -> bool:
    if topic.learning_state not in {"future", "current", "taught"}:
        return True
    if topic.learning_state in {"current", "taught"}:
        if subject_in_semester:
            return True
        if not topic.lesson_starts_on:
            return True
        return today >= topic.lesson_starts_on
    return True

def _topic_available_for_review(topic: Topic, curr: date, subject_in_semester: bool = False) -> bool:
    if topic.learning_state not in {"future", "current", "taught"}:
        return True
    if topic.learning_state in {"current", "taught"}:
        if subject_in_semester:
            return True
        if not topic.lesson_starts_on:
            return True
        return curr >= topic.lesson_starts_on
    if not topic.lesson_starts_on:
        return True
    return curr >= topic.lesson_starts_on

def _subject_in_semester(today: date, topics: Sequence[Topic]) -> bool:
    if any(topic.learning_state == "current" for topic in topics):
        return True
    starts = [topic.lesson_starts_on for topic in topics if topic.lesson_starts_on]
    if not starts:
        return False
    ends = [topic.lesson_ends_on or topic.lesson_starts_on for topic in topics if topic.lesson_starts_on]
    return min(starts) <= today <= max(ends)

def _coverage_reason(topic: Topic, partial: bool) -> str:
    if partial:
        return "Ôn lại phần vừa học trên lớp trong topic này."
    if topic.learning_state == "current":
        return "Ôn lại topic vừa học trên lớp."
    return "Ôn lại topic theo tiến độ syllabus."

def _review_reason_prefix(topic: Topic, partial: bool) -> str:
    if partial:
        return "Ôn tập các mục con đã học trong topic."
    return f"Ôn tập topic {topic.learning_state or 'available'}."

def _simulate_successful_task(
    topic: Topic,
    scope_child_ids: Sequence[str],
    topic_by_id: Mapping[str, Topic],
    curr: date,
    scheduler: Any,
    sprint: bool = False,
) -> None:
    _simulate_successful_session(topic, curr, scheduler, sprint=sprint)
    for child_id in scope_child_ids:
        child = topic_by_id.get(child_id)
        if child and child.id != topic.id:
            _simulate_successful_session(child, curr, scheduler, sprint=sprint)

def _simulate_successful_session(topic: Topic, curr: date, scheduler: Any, sprint: bool = False) -> None:
    try:
        previous_mastery = float(topic.mastery or 0.0)
        # Future planning uses a conservative success assumption so cold-start
        # mastery does not spam too many sessions before the learner has real data.
        simulate_objective_success(
            topic,
            "system_quiz",
            total_questions=SIMULATED_FUTURE_QUIZ_TOTAL_QUESTIONS,
            correct_questions=SIMULATED_FUTURE_QUIZ_CORRECT_QUESTIONS,
        )
        FSRSScheduler.update(topic, "Good", curr, scheduler)
        topic.fsrs_due_date = _due_date_from_card(topic)
        spacing_days = _sprint_spacing_days(previous_mastery) if sprint else MIN_CONTINUOUS_REVIEW_SPACING_DAYS
        spacing_due = curr + timedelta(days=spacing_days)
        if not topic.fsrs_due_date or topic.fsrs_due_date < spacing_due:
            topic.fsrs_due_date = spacing_due
        topic.cost_mins = _cost_from_mastery(topic.mastery)
    except Exception:
        return


def _sprint_spacing_days(mastery: float) -> int:
    if mastery < 0.50:
        return SPRINT_REVIEW_WEAK_SPACING_DAYS
    if mastery < 0.70:
        return SPRINT_REVIEW_MEDIUM_SPACING_DAYS
    return SPRINT_REVIEW_STRONG_SPACING_DAYS

def _due_date_from_card(topic: Topic) -> date | None:
    due = topic.fsrs_card.get("due") or topic.fsrs_card.get("due_date")
    if not due:
        return topic.fsrs_due_date
    try:
        return datetime.fromisoformat(str(due).replace("Z", "+00:00")).date()
    except Exception:
        return topic.fsrs_due_date


def _allocate_minutes(
    items: Sequence[T],
    budget: int,
    weight_fn: Callable[[T], float],
) -> list[tuple[T, int]]:
    min_minutes = settings.MIN_DAILY_TASK_MINUTES
    max_minutes = settings.MAX_DAILY_TASK_MINUTES
    if not items or budget < min_minutes:
        return []

    selected = list(items[: max(1, budget // min_minutes)])
    allocations = [min_minutes for _ in selected]
    remaining = min(budget - sum(allocations), len(selected) * (max_minutes - min_minutes))
    if remaining <= 0:
        return list(zip(selected, allocations))

    weights = [max(0.0, float(weight_fn(item))) for item in selected]
    if not sum(weights):
        weights = [1.0 for _ in selected]
    total_weight = sum(weights)
    raw_extras = [remaining * weight / total_weight for weight in weights]
    extras = [min(max_minutes - min_minutes, int(extra)) for extra in raw_extras]
    allocations = [base + extra for base, extra in zip(allocations, extras)]

    leftover = budget - sum(allocations)
    order = sorted(range(len(selected)), key=lambda index: raw_extras[index] - int(raw_extras[index]), reverse=True)
    while leftover > 0 and order:
        changed = False
        for index in order:
            if leftover <= 0:
                break
            if allocations[index] < max_minutes:
                allocations[index] += 1
                leftover -= 1
                changed = True
        if not changed:
            break
    return list(zip(selected, allocations))
