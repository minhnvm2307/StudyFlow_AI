from __future__ import annotations
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class QuizQuestion(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    id: str
    session_id: str
    topic_id: str
    user_id: str = ""
    prompt: str
    options: list[str]
    correct_option: str
    explanation: str = ""
    source: str = ""
    selected_option: str | None = None
    is_correct: bool | None = None
    reported: bool = False


class QuizSession(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    id: str
    subject_id: str
    task_id: str
    user_id: str = ""
    is_diagnostic: bool = False
    questions: list[QuizQuestion] = []
    submitted_at: str | None = None
    correct: int | None = None
    total: int | None = None
    xp_earned: int | None = None
    feedback: str | None = None


class QuizAnswer(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    question_id: str
    selected_option: str
    reported: bool = False


class SessionResult(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    session_id: str
    correct: int
    total: int
    xp_earned: int
    mastery_delta: list[dict] = []
    next_task: dict | None = None
    feedback: str = ""
