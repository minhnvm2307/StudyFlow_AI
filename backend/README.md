# StudyFlow Backend

This is the single runtime backend for the project. It combines the original scheduling backend with the course, RAG, chat, quiz, and flashcard APIs that previously lived in the old Express MVP backend.

## Stack

- FastAPI + asyncpg
- PostgreSQL as the only app database
- Alembic migrations
- Lexical RAG over Postgres `document_chunks`

The legacy JSON-file backend has been removed. Runtime data now lives in PostgreSQL.

## Quick Start

### 1. Start PostgreSQL

```bash
docker run -d \
  --name studyflow-pg \
  -e POSTGRES_USER=studyflow \
  -e POSTGRES_PASSWORD=studyflow \
  -e POSTGRES_DB=studyflow \
  -p 5432:5432 \
  -v studyflow-pg-data:/var/lib/postgresql/data \
  postgres:16
```

### 2. Install backend dependencies

```bash
python -m pip install -r backend/requirements.txt
```

### 3. Run migrations

```bash
python -c "from alembic.config import main; main(argv=['-c','backend/alembic.ini','upgrade','head'])"
```

From inside `backend`, this also works when the Alembic CLI is on PATH:

```bash
alembic upgrade head
```

For a destructive local reset only, run:

```bash
python backend/scripts/create_schema.py --reset
```

### 4. Run the API

```bash
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 4000 --reload
```

The root dev command starts this backend plus the frontend:

```bash
npm run dev
```

## Environment

Set these in `.env` or your shell:

```env
DATABASE_URL=postgresql://studyflow:studyflow@localhost:5432/studyflow
HOST=0.0.0.0
PORT=4000
CUSTOM_URL=http://localhost:20128/v1
LLM_MODEL=gemini/gemini-3.1-flash-lite-preview
CUSTOM_API_KEY=your-key-here
```

## Unified Schema

Core scheduling tables:

- `users`
- `subjects`
- `topics`
- `study_tasks`
- `quiz_sessions`
- `quiz_questions`
- `fsrs_review_logs`
- `session_mastery_deltas`

Course/RAG compatibility tables:

- `course_sources`
- `document_chunks`
- `chat_threads`
- `chat_messages`
- `practice_quizzes`
- `practice_quiz_results`
- `flashcards`
- `flashcard_sessions`
- `mastery_records`

The public `/api/courses` facade stores courses in `subjects`. Existing scheduler APIs keep using `subjects`, `topics`, and `study_tasks` directly.

## Compatibility API

Frontend-compatible routes are served by FastAPI:

- `/api/courses`, `/api/courses/{courseId}`
- `/api/courses/{courseId}/sources`, `/api/sources/{sourceId}`
- `/api/courses/{courseId}/topics`
- `/api/tasks`, `/api/schedule/reschedule`
- `/api/chat-threads`, `/api/chat`
- `/api/quizzes/generate`, `/api/quiz-results`
- `/api/flashcards/generate`, `/api/flashcard-sessions`, `/api/flashcards/{id}/review`
- `/api/dashboard`, `/api/health`, `/api/dev/clear`, `/api/dev/reset`

`/api/chat` dispatches by body shape: `{ "courseId": "...", "message": "..." }` uses course RAG, while `{ "messages": [...] }` keeps the generic study companion behavior.

## Testing

```bash
python -m pytest backend/scripts/test/test_checkpoints.py backend/test -q
python -m compileall backend/app backend/scripts
npm --prefix frontend run build
```

For the deterministic eval gate that now covers scheduler and mastery logic:

```bash
python scripts/run_eval_scorecard.py
```

This writes `artifacts/eval/scorecard.md` and `artifacts/eval/scorecard.json`.

To include the live RAG integration eval as well:

```bash
ENABLE_ONLINE_EVAL=1 python scripts/run_eval_scorecard.py --include-online
```

To seed a synthetic cohort when you do not have real learners yet:

```bash
python scripts/seed_synthetic_eval.py --reset --users 6 --history-days 28
```

This creates deterministic fake users, fake courses, fake topics, fake chunks, fake quizzes, `mastery_events`, `fsrs_review_logs`, and a cohort report at `artifacts/eval/synthetic_cohort.md`.

To remove a synthetic cohort by prefix without reseeding:

```bash
python scripts/seed_synthetic_eval.py --cleanup-only --prefix synthetic-eval
```

With PostgreSQL running and migrated, run the UI tests:

```bash
npm --prefix frontend run test:ui
```

## Scheduler Docs

See [SCHEDULER_DOCUMENT.md](./SCHEDULER_DOCUMENT.md) for scheduling details: CP-SAT or greedy coverage fallback, FSRS-6, BKT, rolling-horizon scheduling, and missed-task rescheduling.
