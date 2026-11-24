import hashlib, secrets, sys, os, traceback, logging
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException, RequestValidationError
from contextlib import asynccontextmanager
from typing import Any
from app.api.deps import authenticate_api_request, clear_current_user
from app.api.routes import router
from app.config import settings
from app.core.observability import configure_observability, ASGIRequestLoggingMiddleware
from app.db.pg_pool import init_pool, close_pool, get_pool
from app.db import repository
from fastapi.staticfiles import StaticFiles

configure_observability()
logger = logging.getLogger("studyflow")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"[STARTUP] StudyFlow AI backend starting (ENV={settings.ENV}, PORT={settings.PORT})")
    try:
        await init_pool()
        pool = get_pool()
        await repository.ensure_admin_user(pool, get_admin_password_hash())
        await repository.ensure_busy_events_table(pool)
        await repository.ensure_topic_mastery_evidence_columns(pool)
        await repository.ensure_mastery_events_table(pool)
        logger.info("[STARTUP] DB pool initialized and schema checks passed")
    except Exception as exc:
        logger.critical(f"[STARTUP] FAILED to initialize DB pool: {exc}", exc_info=True)
        raise
    yield
    logger.info("[SHUTDOWN] Closing DB pool")
    await close_pool()

def get_admin_password_hash() -> str:
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", b"admin", salt.encode(), 100000).hex()
    return f"{salt}${h}"


SNAKE_TO_CAMEL_MAP = {
    "onboarding_step": "onboardingStep",
    "goal_mode": "goalMode",
    "daily_goal_minutes": "dailyGoalMinutes",
    "study_days": "studyDays",
    "study_window": "studyWindow",
    "quiet_hours": "quietHours",
    "mascot_tone": "mascotTone",
    "fsrs_custom_weights": "fsrsCustomWeights",
    "fsrs_tuning": "fsrsTuning",
    "last_run_at": "lastRunAt",
    "last_rmse": "lastRmse",
    "review_count_at_last_run": "reviewCountAtLastRun",
    "exam_date": "examDate",
    "weekly_goal_minutes": "weeklyGoalMinutes",
    "days_available": "daysAvailable",
    "is_priority": "isPriority",
    "subject_id": "subjectId",
    "topic_id": "topicId",
    "topic_title": "topicTitle",
    "duration_minutes": "durationMinutes",
    "scheduled_date": "scheduledDate",
    "fsrs_card": "fsrsCard",
    "awaiting_diagnostic": "awaitingDiagnostic",
    "mastery_confidence": "masteryConfidence",
    "mastery_evidence_source": "masteryEvidenceSource",
    "confidence_percent": "confidencePercent",
    "section_number": "sectionNumber",
    "content_chunk": "contentChunk",
    "merged_from": "mergedFrom",
    "question_id": "questionId",
    "selected_option": "selectedOption",
    "session_id": "sessionId",
    "xp_earned": "xpEarned",
    "mastery_delta": "masteryDelta",
    "next_task": "nextTask",
    "today_tasks": "todayTasks",
    "coverage_warning": "coverageWarning",
    "source_type": "sourceType",
    "raw_text": "rawText",
    "parsed_json": "parsedJson",
    "current_lesson_id": "currentLessonId",
    "current_week": "currentWeek",
    "join_position": "joinPosition",
    "week_number": "weekNumber",
    "lesson_number": "lessonNumber",
    "assigned_readings": "assignedReadings",
    "starts_on": "startsOn",
    "ends_on": "endsOn",
    "order_idx": "orderIdx",
    "lesson_id": "lessonId",
    "lesson_title": "lessonTitle",
    "learning_state": "learningState",
    "practice_allowed": "practiceAllowed",
    "active_behavior": "activeBehavior",
    "exam_sprint_starts_at": "examSprintStartsAt",
    "syllabus_status": "syllabusStatus",
    "current_lesson": "currentLesson",
    "mapping_summary": "mappingSummary",
    "mascot_message": "mascotMessage",
    "user_id": "userId",
}


def value_map(v: Any) -> Any:
    return v


def keys_to_camel(d: Any) -> Any:
    if isinstance(d, list):
        return [keys_to_camel(i) for i in d]
    if isinstance(d, dict):
        return {SNAKE_TO_CAMEL_MAP.get(k, k): keys_to_camel(value_map(v)) for k, v in d.items()}
    return value_map(d)


class CamelJSONResponse(JSONResponse):
    def render(self, content: Any) -> bytes:
        return super().render(keys_to_camel(content))


is_prod = settings.ENV == "production"

app = FastAPI(
    title="StudyFlow AI",
    version="1.0.0",
    default_response_class=CamelJSONResponse,
    lifespan=lifespan,
    docs_url=None if is_prod else "/docs",
    redoc_url=None if is_prod else "/redoc",
    openapi_url=None if is_prod else "/openapi.json",
)


# ── Global exception handlers ─────────────────────────────────────────────────
# These guarantee that the server NEVER returns an HTML page.
# Railway (and any reverse proxy) may return HTML on 502/504, but if the Python
# process itself handles the request these handlers fire first.

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logger.warning(
        f"[HTTP_EXC] {request.method} {request.url.path} → {exc.status_code}: {exc.detail}"
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail, "status": exc.status_code, "path": request.url.path},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    body_preview = ""
    try:
        body_preview = (await request.body()).decode("utf-8", errors="replace")[:500]
    except Exception:
        pass
    logger.warning(
        f"[VALIDATION_EXC] {request.method} {request.url.path} body={body_preview!r} errors={exc.errors()}"
    )
    return JSONResponse(
        status_code=422,
        content={"error": "Validation error", "detail": exc.errors(), "path": request.url.path},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    tb = traceback.format_exc()
    logger.error(
        f"[UNHANDLED_EXC] {request.method} {request.url.path} → {type(exc).__name__}: {exc}\n{tb}"
    )
    body = {
        "error": f"{type(exc).__name__}: {exc}",
        "path": request.url.path,
        "status": 500,
    }
    if settings.ENV != "production":
        body["traceback"] = tb
    return JSONResponse(status_code=500, content=body)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(ASGIRequestLoggingMiddleware)


@app.middleware("http")
async def auth_context_middleware(request: Request, call_next):
    auth_token = None
    try:
        auth_token = await authenticate_api_request(request)
    except HTTPException as exc:
        return await http_exception_handler(request, exc)

    try:
        return await call_next(request)
    finally:
        clear_current_user(auth_token)

app.router.routes.extend(router.routes)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
