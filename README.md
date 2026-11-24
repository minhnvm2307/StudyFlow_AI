# StudyFlow AI

StudyFlow AI is a study-planning and retrieval-assisted learning app. The active runtime is the FastAPI backend in `backend/`, a PostgreSQL database, and the Vite/React frontend in `frontend/`. The old Express MVP backend has been removed after its course, RAG, chat, quiz, and flashcard APIs were consolidated into FastAPI.


## Documentation

Main project documentation is organized under `docs/`:

- Architecture diagrams index: [docs/diagram/README.md](docs/diagram/README.md)
- Editable architecture source: [docs/diagram/studyflow-architecture.drawio](docs/diagram/studyflow-architecture.drawio)
- Eval report PDF: [docs/eval-report.pdf](docs/eval-report.pdf)
- Eval report source: [docs/eval-report.tex](docs/eval-report.tex)
- Eval evidence snapshot: [docs/eval-evidence](docs/eval-evidence)
- Weekly project worklog: [docs/worklog-2026-06-01-to-2026-07-07.md](docs/worklog-2026-06-01-to-2026-07-07.md)

Quick navigation inside the diagram set:

- System overview: [docs/diagram/README.md#system-overview](docs/diagram/README.md#system-overview)
- Runtime/container view: [docs/diagram/README.md#runtime-container-view](docs/diagram/README.md#runtime-container-view)
- Backend internal architecture: [docs/diagram/README.md#backend-internal-architecture](docs/diagram/README.md#backend-internal-architecture)
- Document and RAG flow: [docs/diagram/README.md#document-and-rag-flow](docs/diagram/README.md#document-and-rag-flow)
- Scheduling and practice feedback loop: [docs/diagram/README.md#scheduling-and-practice-feedback-loop](docs/diagram/README.md#scheduling-and-practice-feedback-loop)

## Architecture

The frontend runs on `http://localhost:5173` and proxies `/api` calls to the FastAPI backend on `http://localhost:4000`. FastAPI exposes compatibility APIs for courses, sources, topic maps, schedules, chat, quizzes, flashcards, and dashboard data. PostgreSQL 16 stores the application state, source metadata, document chunks, topics, tasks, chat history, quizzes, and flashcards.

LLM-backed features use an OpenAI-compatible client configured through environment variables. OpenRouter, NVIDIA, OpenAI, or a custom compatible endpoint can be used. Document uploads are stored locally by default, with optional S3-compatible storage variables available.

## Prerequisites

- Python 3.11+
- Node.js 20+
- PostgreSQL 16, either local or Docker
- PowerShell on Windows, or an equivalent shell on Linux/macOS

## Setup

1. Install repository tooling and copy environment variables.

```powershell
copy .env.example .env
```

2. Start PostgreSQL with Docker.

```powershell
docker run -d `
  --name studyflow-pg `
  -e POSTGRES_USER=studyflow `
  -e POSTGRES_PASSWORD=studyflow `
  -e POSTGRES_DB=studyflow `
  -p 5432:5432 `
  -v studyflow-pg-data:/var/lib/postgresql/data `
  postgres:16
```

3. Install backend and frontend dependencies.

```powershell
python -m pip install -r backend/requirements.txt
npm --prefix frontend install
```

4. Run database migrations.

```powershell
python -c "from alembic.config import main; main(argv=['-c','backend/alembic.ini','upgrade','head'])"
```

For a destructive local reset only:

```powershell
python backend/scripts/create_schema.py --reset
```

5. Optionally seed demo data.

```powershell
npm run seed
```

6. Start the app.

```powershell
npm run dev
```

The dev runner starts FastAPI with 2 backend workers by default, so long-running course onboarding work does not block ordinary reads such as the course list. To change that count:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run-dev.ps1 -BackendWorkers 3
```

When using `-Reload`, the script falls back to 1 backend worker because Uvicorn reload mode is single-worker.

Default URLs:

- Frontend: `http://localhost:5173`
- Backend: `http://localhost:4000`
- Health check: `http://localhost:4000/api/health`

## Environment Variables

Use `.env.example` as the starting point. Do not commit real API keys.

### Database and Server

```env
DATABASE_URL=postgresql://studyflow:studyflow@localhost:5432/studyflow
HOST=0.0.0.0
PORT=4000
APP_ENV=development
```

### Frontend

The Vite dev server proxies `/api` and `/uploads` to `http://127.0.0.1:4000`. For non-proxy deployments, set:

```env
VITE_API_BASE_URL=http://localhost:4000
```

### LLM Provider

Select one provider. The backend normalizes provider-specific values into an OpenAI-compatible request shape.

```env
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-your-key
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=openai/gpt-4o-mini
OPENROUTER_REFERER=http://localhost:5173
OPENROUTER_APP_TITLE=StudyFlow AI
```

```env
LLM_PROVIDER=nvidia
NVIDIA_API_KEY=your-key
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
NVIDIA_MODEL=meta/llama-3.1-8b-instruct
```

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-your-key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
```

```env
LLM_PROVIDER=custom
CUSTOM_URL=http://localhost:20128/v1
CUSTOM_API_KEY=your-key
LLM_MODEL=your-model
LLM_TOP_P=0.9
LLM_MAX_TOKENS=1200
LLM_TIMEOUT_MS=30000
```

### Document, RAG, and Topic Extraction

```env
MAX_SECTIONS_PER_SUBJECT=10
MAX_DOCUMENT_CHARS_FOR_LLM=25000
TOPIC_EXTRACTION_MODE=llm
LLM_TOPICS_MAX_PER_CHAPTER=3
LLM_TOPICS_MAX_PER_SOURCE=36
LLM_TOPIC_CHARS_PER_CHAPTER=6000
MERGE_JACCARD_THRESHOLD=0.75
LOW_INFO_DOC_CHAR_THRESHOLD=300
```

### Scheduler and Review

```env
MAX_DAILY_TASK_MINUTES=45
MIN_DAILY_TASK_MINUTES=5
DEFAULT_DAILY_GOAL_MINUTES=30
TOP_TOPICS_PER_DAY=3
CP_SOLVER_TIMEOUT=5.0
CP_MAX_SLACK_PERCENT=0.20
FSRS_TUNING_THRESHOLD=1000
XP_PER_CORRECT_ANSWER=10
```

### Logging and Optional S3 Storage

```env
LOG_LEVEL=INFO
LOG_DIR=logs
LOG_TO_FILE=true
LOG_BODIES=true
LOG_BODY_MAX_CHARS=20000

S3_BUCKET_NAME=
S3_REGION=
S3_ENDPOINT_URL=
S3_ACCESS_KEY_ID=
S3_SECRET_ACCESS_KEY=
```

## Sample API Queries

These examples assume the backend is running on `http://127.0.0.1:4000`.

```powershell
$base = "http://127.0.0.1:4000"
$auth = Invoke-RestMethod -Uri "$base/api/auth/register" `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"email":"manual-demo@example.com","username":"manual-demo","password":"pass_123"}'
$headers = @{ Authorization = "Bearer $($auth.accessToken)" }
```

Health check:

```powershell
Invoke-RestMethod -Uri "$base/api/health" -Method Get
```

Reset demo data:

```powershell
Invoke-RestMethod -Uri "$base/api/dev/reset" -Method Post
```

Create a course:

```powershell
$course = Invoke-RestMethod -Uri "$base/api/courses" `
  -Method Post `
  -Headers $headers `
  -ContentType "application/json" `
  -Body '{"name":"Biology Final Review","mode":"exam_sprint","priority":"high","targetScore":90,"examDate":"2026-07-20","autoGeneratePlan":false}'
$course.id
```

Add a text source:

```powershell
$notes = "Chapter 1: Plant Energy`n`nTopic: Photosynthesis`n`nPhotosynthesis converts light energy, carbon dioxide, and water into glucose and oxygen. Chlorophyll inside chloroplasts captures light energy."
$source = Invoke-RestMethod -Uri "$base/api/courses/$($course.id)/sources" `
  -Method Post `
  -Headers $headers `
  -ContentType "application/json" `
  -Body (@{ filename="biology-notes.txt"; fileType="txt"; text=$notes } | ConvertTo-Json)
$source.id
```

Generate topic map:

```powershell
Invoke-RestMethod -Uri "$base/api/courses/$($course.id)/generate-topic-map" `
  -Method Post `
  -Headers $headers `
  -ContentType "application/json" `
  -Body '{}'
```

Generate study plan:

```powershell
Invoke-RestMethod -Uri "$base/api/courses/$($course.id)/generate-plan" `
  -Method Post `
  -Headers $headers `
  -ContentType "application/json" `
  -Body '{"availability":["T2","T3","T4","T5","T6"],"sessionMinutes":30,"preferredStartTime":"19:00"}'
```

Ask RAG chat:

```powershell
Invoke-RestMethod -Uri "$base/api/chat" `
  -Method Post `
  -Headers $headers `
  -ContentType "application/json" `
  -Body (@{ courseId=$course.id; message="Explain photosynthesis from my notes."; selectedSourceIds=@($source.id) } | ConvertTo-Json)
```

Generate quiz:

```powershell
Invoke-RestMethod -Uri "$base/api/quizzes/generate" `
  -Method Post `
  -Headers $headers `
  -ContentType "application/json" `
  -Body (@{ courseId=$course.id; selectedSourceIds=@($source.id); query="photosynthesis"; count=3 } | ConvertTo-Json)
```

Generate flashcards:

```powershell
Invoke-RestMethod -Uri "$base/api/flashcards/generate" `
  -Method Post `
  -Headers $headers `
  -ContentType "application/json" `
  -Body (@{ courseId=$course.id; selectedSourceIds=@($source.id); query="chloroplast"; count=2 } | ConvertTo-Json)
```

## Tests

Run backend checks:

```powershell
python -m pytest backend/scripts/test/test_checkpoints.py backend/test -q
python -m compileall backend/app backend/scripts
```

Run frontend build:

```powershell
npm --prefix frontend run build
```

Run UI tests when PostgreSQL, backend, and frontend are already running:

```powershell
npm --prefix frontend run test:ui
```

## Useful Scripts

- `npm run dev`: starts FastAPI and Vite together.
- `npm run seed`: seeds demo data through `backend/scripts/seed_demo.py`.
- `npm run seed:mac-lenin`: seeds the included Mac-Lenin learning material.
- `python backend/scripts/reindex_topics.py`: reindexes topics for existing sources.
