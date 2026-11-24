"""Pure urgency scoring — no I/O, no DB imports."""
from __future__ import annotations
from datetime import date

import fsrs

from app.config import settings


def compute_urgency(
    topic: dict,
    today: date,
    exam_date: date,
    scheduler: fsrs.Scheduler,
    is_priority: bool,
) -> float:
    """
    Urgency = W1*weakness + W2*exam_factor + W3*importance + W4*forgetting_risk
    topic dict must have: mastery, fsrs_card, fsrs_stability, fsrs_last_review
    """
    from app.core.scheduler.fsrs_engine import FSRSScheduler
    from app.schemas.topic import Topic

    # Build a lightweight Topic proxy
    t = Topic(
        id=topic["id"], subject_id="", user_id="",
        title=topic.get("title", ""),
        mastery=topic.get("mastery", 0.15),
        fsrs_card=topic.get("fsrs_card", {}),
        fsrs_stability=topic.get("fsrs_stability", 0.0),
        fsrs_last_review=topic.get("fsrs_last_review"),
    )

    weakness = 1.0 - t.mastery
    days_left = max(1, (exam_date - today).days)
    exam_factor = 1.0 / days_left
    importance = 2.0 if is_priority else 1.0
    retention = FSRSScheduler.get_retention(t, today, scheduler)
    forgetting_risk = 1.0 - retention

    W1 = settings.URGENCY_W1_WEAKNESS
    W2 = settings.URGENCY_W2_EXAM_FACTOR
    W3 = settings.URGENCY_W3_IMPORTANCE
    W4 = settings.URGENCY_W4_FORGETTING

    return W1 * weakness + W2 * exam_factor + W3 * importance + W4 * forgetting_risk


class PriorityScheduler:
    """Thin wrapper kept for backward-compat with existing callers."""

    def urgency(
        self,
        topic,
        today: date,
        exam_date: date,
        scheduler: fsrs.Scheduler,
        is_priority: bool,
    ) -> dict:
        score = compute_urgency(topic.__dict__ | {"id": topic.id}, today, exam_date, scheduler, is_priority)
        weakness = 1.0 - topic.mastery
        from app.core.scheduler.fsrs_engine import FSRSScheduler
        retention = FSRSScheduler.get_retention(topic, today, scheduler)
        return {"urgency": score, "forgetting_risk": 1.0 - retention, "weakness": weakness}

    def slice_session(self, tasks: list, budget: int) -> list:
        """Trim today's tasks to fit the given budget without re-running FSRS/BKT."""
        result, used = [], 0
        for t in sorted(tasks, key=lambda x: getattr(x, "duration_minutes", 0)):
            if used + t.duration_minutes <= budget:
                result.append(t)
                used += t.duration_minutes
        return result
