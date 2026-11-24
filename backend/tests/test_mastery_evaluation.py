import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas import Topic
import app.services.mastery_service as mastery_service
from app.services.mastery_service import (
    BatchQuestionOutcome,
    apply_objective_batch,
    recompute_confidence,
    simulate_objective_success,
)


def test_simulate_objective_success_increases_mastery_and_confidence():
    topic = Topic(
        id="topic-mastery-1",
        subject_id="subject-1",
        user_id="user-1",
        title="Binary mastery",
        mastery=0.20,
        mastery_confidence=0.0,
        is_learned=False,
        awaiting_diagnostic=True,
    )

    before = topic.mastery
    after = simulate_objective_success(topic, total_questions=10, correct_questions=9)

    assert after > before
    assert topic.mastery == after
    assert topic.mastery_confidence > 0.0
    assert topic.is_learned is True
    assert topic.practice_allowed is True
    assert 10 <= topic.cost_mins <= 30


def test_apply_objective_batch_logs_one_event_per_outcome_and_updates_topic(monkeypatch):
    recorded_events = []

    async def fake_append_mastery_event(**kwargs):
        recorded_events.append(kwargs)

    monkeypatch.setattr(mastery_service.repository, "append_mastery_event", fake_append_mastery_event)

    topic = Topic(
        id="topic-batch-1",
        subject_id="subject-1",
        user_id="user-1",
        title="Objective batch",
        mastery=0.35,
        mastery_confidence=0.0,
        is_learned=False,
    )
    outcomes = [
        BatchQuestionOutcome(correct=True, question_format="mcq_4"),
        BatchQuestionOutcome(correct=False, question_format="mcq_4"),
        BatchQuestionOutcome(correct=True, question_format="mcq_2"),
    ]

    result = asyncio.run(
        apply_objective_batch(
            None,
            topic,
            user_id="user-1",
            subject_id="subject-1",
            source_type="system_quiz",
            source_id="quiz-batch-1",
            outcomes=outcomes,
            is_diagnostic=False,
        )
    )

    assert len(recorded_events) == len(outcomes)
    assert topic.mastery == result["after"]
    assert topic.mastery_confidence == result["confidence"]
    assert topic.mastery > result["before"]
    assert topic.mastery_evidence_source == "system_quiz"
    assert topic.is_learned is True
    assert 10 <= topic.cost_mins <= 30

    first_event = recorded_events[0]
    last_event = recorded_events[-1]
    assert first_event["predicted_p_correct"] > 0.0
    assert first_event["actual_correct"] is True
    assert last_event["actual_correct"] is True
    assert first_event["question_format"] == "mcq_4"
    assert last_event["question_format"] == "mcq_2"
    assert first_event["p_l_after"] == topic.mastery


def test_recompute_confidence_ignores_sources_that_do_not_update_confidence(monkeypatch):
    now = datetime.now(timezone.utc)

    async def flashcard_only(*_args, **_kwargs):
        return [
            {
                "source_id": "flashcard-1",
                "source_type": "flashcard",
                "question_format": "flashcard",
                "is_diagnostic": False,
                "predicted_p_correct": 0.6,
                "actual_correct": True,
                "created_at": now,
            }
        ]

    monkeypatch.setattr(mastery_service.repository, "get_recent_mastery_events", flashcard_only)

    confidence = asyncio.run(recompute_confidence(None, "topic-1", "user-1"))

    assert confidence == 0.0


def test_recompute_confidence_groups_recent_objective_evidence(monkeypatch):
    now = datetime.now(timezone.utc)

    async def mixed_events(*_args, **_kwargs):
        return [
            {
                "source_id": "quiz-batch-2",
                "source_type": "system_quiz",
                "question_format": "mcq_4",
                "is_diagnostic": False,
                "predicted_p_correct": 0.55,
                "actual_correct": True,
                "created_at": now,
            },
            {
                "source_id": "quiz-batch-2",
                "source_type": "system_quiz",
                "question_format": "mcq_4",
                "is_diagnostic": False,
                "predicted_p_correct": 0.55,
                "actual_correct": False,
                "created_at": now - timedelta(minutes=2),
            },
            {
                "source_id": "self-1",
                "source_type": "self_assessment",
                "question_format": "mcq_4",
                "is_diagnostic": False,
                "predicted_p_correct": 0.50,
                "actual_correct": True,
                "created_at": now - timedelta(days=1),
            },
        ]

    monkeypatch.setattr(mastery_service.repository, "get_recent_mastery_events", mixed_events)

    confidence = asyncio.run(recompute_confidence(None, "topic-1", "user-1"))

    assert 0.0 < confidence < 1.0
