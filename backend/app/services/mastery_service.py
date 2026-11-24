from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Iterable

import asyncpg

from app.db import repository


SOURCE_RULES: dict[str, dict[str, Any]] = {
    "entry_diagnostic_quiz": {
        "mastery_weight": 1.00,
        "confidence_strength": 0.95,
        "updates_mastery": True,
        "updates_confidence": True,
        "updates_fsrs": True,
        "objective": True,
    },
    "system_quiz": {
        "mastery_weight": 0.90,
        "confidence_strength": 0.90,
        "updates_mastery": True,
        "updates_confidence": True,
        "updates_fsrs": True,
        "objective": True,
    },
    "workspace_quiz": {
        "mastery_weight": 0.60,
        "confidence_strength": 0.60,
        "updates_mastery": True,
        "updates_confidence": True,
        "updates_fsrs": True,
        "objective": True,
    },
    "scored_review": {
        "mastery_weight": 0.90,
        "confidence_strength": 0.90,
        "updates_mastery": True,
        "updates_confidence": True,
        "updates_fsrs": True,
        "objective": True,
    },
    "self_assessment": {
        "mastery_weight": 0.00,
        "confidence_strength": 0.45,
        "updates_mastery": False,
        "updates_confidence": True,
        "updates_fsrs": False,
        "objective": False,
    },
    "flashcard": {
        "mastery_weight": 0.00,
        "confidence_strength": 0.00,
        "updates_mastery": False,
        "updates_confidence": False,
        "updates_fsrs": True,
        "objective": False,
    },
}

CONFIDENCE_OBJECTIVE_EXIT_THRESHOLD = 0.60
CONFIDENCE_WINDOW_DAYS = 60
CONFIDENCE_WINDOW_GROUPS = 12
CONFIDENCE_RECENCY_HALF_LIFE_DAYS = 45
OBJECTIVE_EVIDENCE_REFERENCE_QUESTIONS = 20
OBJECTIVE_EVIDENCE_CAP = 1.25
OBJECTIVE_EVIDENCE_EXPONENT = 0.35
SIMULATION_BASELINE_QUESTIONS = 20
SIMULATION_EQUIVALENT_QUESTIONS = 40


@dataclass
class BatchQuestionOutcome:
    correct: bool
    question_format: str = "mcq_4"


def predict_p_correct(mastery: float, p_g: float, p_s: float) -> float:
    return mastery * (1 - p_s) + (1 - mastery) * p_g


def source_rule(source_type: str) -> dict[str, Any]:
    return SOURCE_RULES.get(source_type, SOURCE_RULES["system_quiz"])


def _objective_evidence_strength(n: int, rule: dict[str, Any]) -> float:
    return float(rule["mastery_weight"]) * min(
        OBJECTIVE_EVIDENCE_CAP,
        (max(1, n) / OBJECTIVE_EVIDENCE_REFERENCE_QUESTIONS) ** OBJECTIVE_EVIDENCE_EXPONENT,
    )


def _compute_confidence_gain(n: int, rule: dict[str, Any]) -> float:
    volume_factor = 1 - math.exp(-max(1, n) / 10)
    return min(0.30, 0.03 + 0.22 * float(rule["confidence_strength"]) * volume_factor)


def _next_confidence(confidence_before: float, n: int, rule: dict[str, Any]) -> float:
    gain = _compute_confidence_gain(n, rule)
    return max(confidence_before, min(0.99, confidence_before + gain * (1 - confidence_before)))


def _compute_objective_mastery_step(topic, rule: dict[str, Any], *, n: int, k: int) -> dict[str, float]:
    mastery_before = float(topic.mastery or 0.0)
    p_t = float(topic.p_t)
    p_g = float(topic.p_g)
    p_s = float(topic.p_s)
    accuracy = k / max(1, n)
    predicted = predict_p_correct(mastery_before, p_g, p_s)
    accuracy_signal = accuracy - predicted
    evidence_strength = _objective_evidence_strength(n, rule)
    positive_gain = 0.18 + 0.22 * evidence_strength + 0.18 * (accuracy ** 2.2)
    positive_saturation = 0.25 + 0.75 * ((1 - mastery_before) ** 0.55)
    negative_gain = 0.10 + 0.18 * evidence_strength
    negative_saturation = 0.30 + 0.70 * mastery_before
    if accuracy_signal >= 0:
        delta = positive_gain * accuracy_signal * positive_saturation
    else:
        delta = negative_gain * accuracy_signal * negative_saturation
    mastery_after = max(0.01, min(0.99, mastery_before + delta))

    return {
        "before": mastery_before,
        "after": mastery_after,
        "predicted": predicted,
        "observed": accuracy,
        "candidate": accuracy,
        "alpha": positive_gain if accuracy_signal >= 0 else negative_gain,
        "volume_strength": evidence_strength,
        "accuracy": accuracy,
        "accuracy_signal": accuracy_signal,
        "p_t_batch": p_t * evidence_strength,
        "p_g": p_g,
        "p_s": p_s,
        "confidence_gain": _compute_confidence_gain(n, rule),
    }


async def apply_objective_batch(
    pool: asyncpg.Pool,
    topic,
    *,
    user_id: str,
    subject_id: str,
    source_type: str,
    source_id: str,
    outcomes: Iterable[BatchQuestionOutcome],
    is_diagnostic: bool,
) -> dict[str, float]:
    rows = list(outcomes)
    if not rows:
        return {"before": topic.mastery, "after": topic.mastery, "confidence": float(getattr(topic, "mastery_confidence", 0.0) or 0.0)}

    rule = source_rule(source_type)
    n = len(rows)
    k = sum(1 for row in rows if row.correct)
    step = _compute_objective_mastery_step(topic, rule, n=n, k=k)
    mastery_before = step["before"]
    mastery_after = step["after"]
    topic.mastery = mastery_after

    for index, row in enumerate(rows):
        await repository.append_mastery_event(
            pool=pool,
            user_id=user_id,
            subject_id=subject_id,
            topic_id=topic.id,
            source_type=source_type,
            source_id=source_id,
            question_format=row.question_format,
            is_diagnostic=is_diagnostic,
            p_l_before=mastery_before,
            p_t_used=step["p_t_batch"],
            p_g_used=step["p_g"],
            p_s_used=step["p_s"],
            predicted_p_correct=step["predicted"],
            actual_correct=row.correct,
            p_l_obs=step["observed"],
            p_l_after=mastery_after,
            excluded=False,
            exclude_reason=None,
        )

    confidence_store = _next_confidence(float(getattr(topic, "mastery_confidence", 0.0) or 0.0), n, rule)
    topic.mastery_confidence = confidence_store
    topic.mastery_evidence_source = source_type
    topic.cost_mins = max(10, min(30, 15 + round((1 - topic.mastery) * 15)))
    topic.is_learned = True
    if confidence_store >= CONFIDENCE_OBJECTIVE_EXIT_THRESHOLD:
        topic.awaiting_diagnostic = False

    return {"before": mastery_before, "after": mastery_after, "confidence": confidence_store}


def apply_self_assessment_seed(topic, score: float) -> dict[str, float]:
    mastery = max(0.0, min(1.0, score / 10.0))
    topic.mastery = mastery
    topic.p_l0 = 0.05
    topic.mastery_confidence = 0.45
    topic.mastery_evidence_source = "self_assessment"
    topic.awaiting_diagnostic = True
    topic.is_learned = True
    topic.cost_mins = max(10, min(30, 15 + round((1 - topic.mastery) * 15)))
    return {"mastery": mastery, "confidence": topic.mastery_confidence}


def simulate_objective_success(topic, source_type: str = "system_quiz", total_questions: int = 3, correct_questions: int | None = None) -> float:
    rule = source_rule(source_type)
    n = max(1, int(total_questions))
    k = max(0, min(n, correct_questions if correct_questions is not None else n))
    effective_n = n
    effective_k = k
    if n <= SIMULATION_BASELINE_QUESTIONS:
        boost_factor = SIMULATION_EQUIVALENT_QUESTIONS / max(1, SIMULATION_BASELINE_QUESTIONS)
        effective_n = max(n, int(round(n * boost_factor)))
        effective_k = max(0, min(effective_n, int(round(k * boost_factor))))
    step = _compute_objective_mastery_step(topic, rule, n=effective_n, k=effective_k)
    topic.mastery = step["after"]
    topic.is_learned = True
    topic.practice_allowed = True
    topic.cost_mins = max(10, min(30, 15 + round((1 - topic.mastery) * 15)))
    confidence_before = float(getattr(topic, "mastery_confidence", 0.0) or 0.0)
    topic.mastery_confidence = _next_confidence(confidence_before, effective_n, rule)
    if topic.mastery_confidence >= CONFIDENCE_OBJECTIVE_EXIT_THRESHOLD:
        topic.awaiting_diagnostic = False
    return topic.mastery


async def recompute_confidence(pool: asyncpg.Pool, topic_id: str, user_id: str) -> float:
    events = await repository.get_recent_mastery_events(pool, topic_id, user_id, CONFIDENCE_WINDOW_DAYS, 256)
    if not events:
        return 0.0

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    newest_by_group: dict[str, datetime] = {}
    for event in events:
        key = str(event["source_id"])
        grouped[key].append(event)
        created_at = event["created_at"]
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        newest = newest_by_group.get(key)
        if newest is None or created_at > newest:
            newest_by_group[key] = created_at

    sorted_groups = sorted(newest_by_group.items(), key=lambda item: item[1], reverse=True)[:CONFIDENCE_WINDOW_GROUPS]
    confidence = 0.0

    for group_id, newest_at in sorted_groups:
        group_events = grouped[group_id]
        source_type = str(group_events[0]["source_type"] or "system_quiz")
        rule = source_rule(source_type)
        if not rule["updates_confidence"]:
            continue
        n_e = len(group_events)
        confidence = _next_confidence(confidence, n_e, rule)

    return max(0.0, min(0.99, confidence))
