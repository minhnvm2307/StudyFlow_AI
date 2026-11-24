from __future__ import annotations
from datetime import datetime, date, timezone
import math
import fsrs
from app.schemas.topic import Topic


def get_scheduler(weights: list[float] | None = None) -> fsrs.Scheduler:
    if weights:
        try:
            return fsrs.Scheduler(parameters=tuple(weights))
        except Exception:
            return fsrs.Scheduler()
    return fsrs.Scheduler()


class FSRSScheduler:
    @staticmethod
    def _card(topic: Topic) -> fsrs.Card:
        if topic.fsrs_card:
            try:
                return fsrs.Card.from_dict(topic.fsrs_card)
            except Exception:
                pass
        return fsrs.Card()

    @staticmethod
    def get_retention(topic: Topic, on: date, scheduler: fsrs.Scheduler) -> float:
        card = FSRSScheduler._card(topic)
        if card.last_review is None:
            return 0.0
        dt = datetime.combine(on, datetime.min.time(), tzinfo=timezone.utc)
        try:
            r = scheduler.get_card_retrievability(card, dt)
            return float(r) if r is not None else 0.0
        except Exception:
            return 0.0

    @staticmethod
    def get_retention_from_card(card_dict: dict, on: date, scheduler: fsrs.Scheduler) -> float:
        try:
            card = fsrs.Card.from_dict(card_dict) if card_dict else fsrs.Card()
        except Exception:
            card = fsrs.Card()
        if card.last_review is None:
            return 0.0
        dt = datetime.combine(on, datetime.min.time(), tzinfo=timezone.utc)
        try:
            r = scheduler.get_card_retrievability(card, dt)
            return float(r) if r is not None else 0.0
        except Exception:
            return 0.0

    @staticmethod
    def update(topic: Topic, rating: str, on: date, scheduler: fsrs.Scheduler) -> None:
        rating_map = {
            "Again": fsrs.Rating.Again,
            "Hard": fsrs.Rating.Hard,
            "Good": fsrs.Rating.Good,
            "Easy": fsrs.Rating.Easy,
        }
        card = FSRSScheduler._card(topic)
        dt = datetime.combine(on, datetime.min.time(), tzinfo=timezone.utc)
        updated_card, _ = scheduler.review_card(card, rating_map.get(rating, fsrs.Rating.Good), dt)
        topic.fsrs_card = updated_card.to_dict()
        topic.fsrs_stability = updated_card.stability or 0.0
        topic.fsrs_difficulty = updated_card.difficulty or 5.0
        topic.fsrs_last_review = on
        topic.fsrs_state = int(updated_card.state) if updated_card.state is not None else 0

    @staticmethod
    def simulate_update(card_dict: dict, rating: str, on: date, scheduler: fsrs.Scheduler) -> dict:
        """Simulate a review in-memory and return new card dict."""
        rating_map = {
            "Again": fsrs.Rating.Again,
            "Hard": fsrs.Rating.Hard,
            "Good": fsrs.Rating.Good,
            "Easy": fsrs.Rating.Easy,
        }
        try:
            card = fsrs.Card.from_dict(card_dict) if card_dict else fsrs.Card()
        except Exception:
            card = fsrs.Card()
        dt = datetime.combine(on, datetime.min.time(), tzinfo=timezone.utc)
        updated_card, _ = scheduler.review_card(card, rating_map.get(rating, fsrs.Rating.Good), dt)
        return updated_card.to_dict()

    @staticmethod
    def get_next_interval(topic: Topic, desired_retention: float = 0.90) -> int:
        stab = topic.fsrs_card.get("stability") or topic.fsrs_stability or 2.0
        return max(1, round(-stab * math.log(desired_retention)))
