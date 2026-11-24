from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class FsrsReviewLog(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    id: str
    user_id: str
    subject_id: str
    item_id: str
    rating: int  # 1=Again 2=Hard 3=Good 4=Easy
    review_date: str | datetime
    elapsed_days: int
    review_state: int = 0  # 0=Learning 1=Review 2=Relearning


class FsrsTuningState(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    last_run_at: str | None = None
    last_rmse: float | None = None
    review_count_at_last_run: int = 0
