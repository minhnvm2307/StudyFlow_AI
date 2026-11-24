from __future__ import annotations
from pydantic import BaseModel, ConfigDict, field_validator
from pydantic.alias_generators import to_camel
from typing import Any


class FsrsTuningState(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    last_run_at: str | None = None
    last_rmse: float | None = None
    review_count_at_last_run: int = 0


class UserProfile(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    id: str
    username: str | None = None
    email: str
    onboarding_step: int = 0
    goal_mode: str | None = None
    daily_goal_minutes: int = 30
    study_days: list[str] = []
    study_window: dict | None = None
    quiet_hours: dict | None = None
    mascot_tone: str = "encouraging"
    notifications: dict = {}
    xp: int = 0
    streak: int = 0
    fsrs_custom_weights: list[float] | None = None
    fsrs_tuning: FsrsTuningState = FsrsTuningState()
    # plan_dirty NOT exposed — internal only
    plan_dirty: bool = False

    @field_validator("fsrs_tuning", mode="before")
    @classmethod
    def parse_fsrs_tuning(cls, v: Any) -> Any:
        if isinstance(v, dict):
            return FsrsTuningState(**v)
        return v
