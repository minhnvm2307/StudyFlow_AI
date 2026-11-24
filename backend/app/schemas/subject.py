from __future__ import annotations
from datetime import date
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class Subject(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    id: str
    user_id: str
    name: str
    mode: str = "semester"
    exam_date: date | None = None
    weekly_goal_minutes: int = 0
    daily_goal_minutes: int = 30
    days_available: list[str] = []
    availability_windows: list[dict] = []
    is_priority: bool = False
    coverage_warning: str | None = None


class SubjectDTO(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    id: str
    user_id: str
    name: str
    mode: str
    exam_date: str | None = None
    weekly_goal_minutes: int
    daily_goal_minutes: int
    days_available: list[str]
    availability_windows: list[dict]
    is_priority: bool
    coverage_warning: str | None = None
