from __future__ import annotations
from datetime import date
from typing import Any
from pydantic import BaseModel, ConfigDict, field_validator
from pydantic.alias_generators import to_camel


class Topic(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    id: str
    subject_id: str
    user_id: str = ""
    title: str
    description: str = ""
    section_number: int = 0
    content_chunk: str = ""
    order_idx: int = 0
    cost_mins: int = 30

    # BKT
    mastery: float = 0.05
    p_l0: float = 0.05
    p_t: float = 0.2
    p_g: float = 0.2
    p_s: float = 0.1
    awaiting_diagnostic: bool = True
    mastery_confidence: float = 0.0
    mastery_evidence_source: str = "none"

    # FSRS
    fsrs_card: dict = {}
    fsrs_stability: float = 0.0
    fsrs_difficulty: float = 5.0
    fsrs_last_review: date | None = None
    fsrs_due_date: date | None = None
    fsrs_state: int = 0  # internal, not in DB column directly

    merged_from: list[str] = []
    is_learned: bool = False
    parent_topic_id: str | None = None
    parent_topic_title: str | None = None
    is_subtopic: bool = True
    lesson_id: str | None = None
    learning_state: str = "taught"
    practice_allowed: bool = True
    lesson_starts_on: date | None = None
    lesson_ends_on: date | None = None

    @field_validator("fsrs_card", mode="before")
    @classmethod
    def parse_fsrs_card(cls, v: Any) -> Any:
        if v is None:
            return {}
        return v


class TopicDTO(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    id: str
    subject_id: str
    title: str
    mastery: int  # round(raw * 100)
    level: str
    due: bool
    weak: bool
    awaiting_diagnostic: bool
    mastery_confidence: float = 0.0
    mastery_evidence_source: str = "none"
    confidence_percent: int = 0
    p_l: float
    fsrs_stability: float
    fsrs_difficulty: float
    fsrs_last_review: str | None
    content_chunk: str

    @staticmethod
    def from_topic(topic: Topic, on: date) -> "TopicDTO":
        mastery_pct = round(topic.mastery * 100)
        if topic.mastery >= 0.85:
            level = "mastered"
        elif topic.mastery >= 0.60:
            level = "good"
        elif topic.mastery >= 0.30:
            level = "progressing"
        else:
            level = "priority"
        due = bool(topic.fsrs_due_date and topic.fsrs_due_date <= on and not topic.awaiting_diagnostic)
        return TopicDTO(
            id=topic.id, subject_id=topic.subject_id, title=topic.title,
            mastery=mastery_pct, level=level, due=due, weak=topic.mastery < 0.4,
            awaiting_diagnostic=topic.awaiting_diagnostic,
            mastery_confidence=topic.mastery_confidence,
            mastery_evidence_source=topic.mastery_evidence_source,
            confidence_percent=round(topic.mastery_confidence * 100),
            p_l=topic.mastery, fsrs_stability=topic.fsrs_stability,
            fsrs_difficulty=topic.fsrs_difficulty,
            fsrs_last_review=topic.fsrs_last_review.isoformat() if topic.fsrs_last_review else None,
            content_chunk=topic.content_chunk,
        )
