import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.cp_solver.coverage_pass import solve_coverage_pass
from app.schemas import Subject, Topic, UserProfile
from app.services.unified_scheduler import ScheduleInput, build_schedule_from_inputs


def test_solve_coverage_pass_assigns_every_topic_when_feasible():
    result = solve_coverage_pass(
        global_pool_new=[
            {"id": "topic-a", "subject_id": "subject-a", "cost_mins": 30, "order_idx": 1},
            {"id": "topic-b", "subject_id": "subject-b", "cost_mins": 30, "order_idx": 1},
        ],
        daily_budget=60,
        horizon=2,
        study_days_map=[True, True],
    )

    scheduled_ids = {
        topic_id
        for plan in result.get("schedule", {}).values()
        for topic_id in plan.get("new_topics", [])
    }

    assert result["status"] == "success"
    assert scheduled_ids == {"topic-a", "topic-b"}
    assert result["is_over_budget"] is False


def test_solve_coverage_pass_respects_subject_order_constraints():
    result = solve_coverage_pass(
        global_pool_new=[
            {"id": "topic-1", "subject_id": "subject-a", "cost_mins": 30, "order_idx": 1},
            {"id": "topic-2", "subject_id": "subject-a", "cost_mins": 30, "order_idx": 2},
        ],
        daily_budget=30,
        horizon=3,
        study_days_map=[True, True, True],
    )

    day_by_topic = {}
    for day_offset, plan in result.get("schedule", {}).items():
        for topic_id in plan.get("new_topics", []):
            day_by_topic[topic_id] = int(day_offset)

    assert result["status"] == "success"
    assert day_by_topic["topic-1"] <= day_by_topic["topic-2"]


def test_build_schedule_from_inputs_marks_over_budget_when_only_fallback_days_work():
    today = date(2026, 7, 6)
    subject = Subject(
        id="subject-1",
        user_id="user-1",
        name="Macroeconomics",
        mode="semester",
        daily_goal_minutes=60,
        days_available=[],
    )
    profile = UserProfile(
        id="user-1",
        email="user@example.com",
        daily_goal_minutes=60,
        study_days=[],
        study_window={"start": "18:00", "end": "22:00"},
    )
    topic = Topic(
        id="topic-1",
        subject_id="subject-1",
        user_id="user-1",
        title="Elasticity",
        order_idx=1,
        mastery=0.2,
        is_learned=False,
        is_subtopic=False,
        learning_state="taught",
        practice_allowed=True,
    )

    result = build_schedule_from_inputs(
        ScheduleInput(
            user_id="user-1",
            today=today,
            profile=profile,
            subjects={"subject-1": subject},
            topic_map={"subject-1": [topic]},
            horizon=3,
            daily_budget=60,
            start_hhmm=(18, 0),
            study_days_map=[False, False, False],
        )
    )

    assert result.status == "success"
    assert result.coverage_warning == "over_budget"
    assert result.blocks
    assert any(block.task.scheduled_date > today + timedelta(days=2) for block in result.blocks)
