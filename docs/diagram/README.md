# StudyFlow Architecture Diagram Set

This folder is the canonical home for the current StudyFlow architecture diagrams.

## Files
- `studyflow-architecture.drawio`: editable multi-page source of truth for the architecture set.

For a quick orientation, start with the system overview, then follow the runtime and feature-flow diagrams.
The diagrams describe the current architecture; use the repository README for setup and run instructions.

## System Overview
Page 1 shows the top-level runtime path from browser to React/Vite, through FastAPI, into PostgreSQL, storage, and the OpenAI-compatible LLM provider.

## Runtime Container View
Page 2 breaks the running system into browser session, frontend runtime, backend runtime, and state/external dependencies. It highlights `App.jsx`, `studyflowApi.js`, the Vite proxy, FastAPI route dispatch, service orchestration, and the asyncpg-backed persistence layer.

## Backend Internal Architecture
Page 3 focuses on the internal backend layering:
- route groups in `backend/app/api/routes/`
- orchestration services such as `course_api_service.py`, `document_service.py`, `syllabus_service.py`, and `unified_scheduler.py`
- core modules for RAG, document processing, scheduling, CP solving, FSRS tuning, and guardrails
- repository, pool, locking, PostgreSQL, and the LLM boundary

## Document and RAG Flow
Page 4 covers the content pipeline from upload or source creation to extraction, chunking, topic extraction, storage, retrieval, context building, grounded generation, and persistence of chat or practice artifacts.

## Scheduling and Practice Feedback Loop
Page 5 shows how configuration, availability, syllabus state, and topic state feed scheduling; how tasks reach dashboard and workspace surfaces; and how quiz or flashcard outcomes update mastery and due dates before the next schedule rebuild.

## Visual Conventions
- Blue: client and UI runtime
- Teal: backend services and orchestration
- Green: persisted state and storage
- Amber: pipeline stages or scheduling logic
- Gray dashed: external dependencies

## Export Status
The current workspace does not have a working `draw.io` CLI binary available, so PNG, SVG, and PDF exports are not checked into the repo from this session.

Open `studyflow-architecture.drawio` in draw.io desktop or diagrams.net to review or export individual pages.
