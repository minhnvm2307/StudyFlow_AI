from __future__ import annotations
from datetime import date, datetime
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class StudyTask(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    id: str
    subject_id: str
    topic_id: str | None = None
    user_id: str = ""
    topic_title: str
    type: str
    duration_minutes: int
    reason: str = ""
    scheduled_date: date
    status: str = "ready"
    day: str | None = None
    title: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    priority: str = "medium"
    lesson_id: str | None = None
    lesson_title: str | None = None
    learning_state: str | None = None
    subtopic_id: str | None = None
    parent_topic_id: str | None = None
    is_partial_topic: bool = False
    scope: str | None = None
    earliest_allowed_at: datetime | None = None


class TaskDTO(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    id: str
    subject_id: str
    topic_id: str
    topic_title: str
    type: str
    duration_minutes: int
    reason: str
    scheduled_date: str
    status: str
    day: str | None = None


class Dashboard(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    subject: dict | None = None
    today_tasks: list[dict] = []
    readiness: float = 0.0
    streak: int = 0
    xp: int = 0
    coverage_warning: str | None = None
    mascot_message: str = ""
