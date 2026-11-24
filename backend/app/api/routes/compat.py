from __future__ import annotations

import os
import json
from datetime import date
from typing import Any

import asyncpg
from pydantic import BaseModel
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response

from app.api.deps import current_user_id
from app.config import settings
from app.core.document.extractor import extract_text_from_file_path, sanitize_text_for_postgres, save_uploaded_file
from app.core.observability import get_logs_summary, get_request_id, log_upload_metadata, logging_status
from app.db.pg_pool import get_pool
from app.services import course_api_service as svc


router = APIRouter()


def _uid(user_id: str | None = None) -> str:
    del user_id
    return current_user_id()


def _raise(error: Exception):
    if isinstance(error, KeyError):
        raise HTTPException(status_code=404, detail=str(error).strip("'"))
    if isinstance(error, ValueError):
        raise HTTPException(status_code=400, detail=str(error))
    raise error


@router.get("/api/health")
async def health():
    return {"ok": True, "service": "studyflow-ai-fastapi", "storage": "postgres", "logging": logging_status()}

@router.get("/api/dev/logs/summary")
async def logs_summary():
    if settings.ENV == "production":
        raise HTTPException(status_code=404, detail="Endpoint not found")
    return get_logs_summary()


@router.post("/api/dev/clear")
async def dev_clear():
    raise HTTPException(status_code=404, detail="Endpoint not found")


@router.post("/api/dev/reset")
async def dev_reset():
    raise HTTPException(status_code=404, detail="Endpoint not found")


@router.get("/api/dashboard")
async def dashboard(user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    return await svc.get_dashboard(pool, _uid(user_id))


@router.get("/api/courses")
async def list_courses(filter: str | None = None, sort: str | None = None, user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    return await svc.list_courses(pool, _uid(user_id), filter, sort)


@router.post("/api/courses", status_code=201)
async def create_course(body: dict[str, Any], user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    try:
        return await svc.create_course(pool, body, _uid(user_id))
    except Exception as error:
        _raise(error)

@router.post("/api/courses/onboarding", status_code=201)
async def create_course_onboarding(background_tasks: BackgroundTasks, request: Request, user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    try:
        form = await request.form()
        syllabus_files = [value for key, value in form.multi_items() if key == "syllabus" and getattr(value, "filename", None)]
        source_files = [value for key, value in form.multi_items() if key == "sources" and getattr(value, "filename", None)]
        if len(syllabus_files) != 1:
            raise ValueError("Upload exactly one syllabus file")
        if not source_files:
            raise ValueError("Upload at least one textbook file")

        course_payload = _json_form_value(form.get("course"), "course")
        syllabus_payload = _json_form_value(form.get("syllabusMeta"), "syllabusMeta")
        course_payload["autoGeneratePlan"] = False
        uid = _uid(user_id)
        await svc.validate_course_semester_overlap_limit(pool, syllabus_payload, uid)
        course = await svc.create_course(pool, course_payload, uid)
        course_id = course["id"]

        syllabus_upload = syllabus_files[0]
        syllabus_filename = getattr(syllabus_upload, "filename", None) or "syllabus.txt"
        syllabus_contents = await syllabus_upload.read()
        log_upload_metadata(get_request_id(), syllabus_filename, getattr(syllabus_upload, "content_type", None), len(syllabus_contents))
        syllabus_storage_path = os.path.abspath(save_uploaded_file(syllabus_filename, syllabus_contents))
        syllabus_payload = {
            **syllabus_payload,
            "mode": "upload",
            "filename": syllabus_filename,
            "storagePath": syllabus_storage_path,
        }
        await svc.create_processing_syllabus(pool, course_id, syllabus_payload, uid)

        source_ids = []
        for upload in source_files:
            filename = getattr(upload, "filename", None) or "upload.txt"
            contents = await upload.read()
            log_upload_metadata(get_request_id(), filename, getattr(upload, "content_type", None), len(contents))
            storage_path = os.path.abspath(save_uploaded_file(filename, contents))
            source = await svc.create_pending_source(pool, course_id, {
                "filename": filename,
                "originalName": filename,
                "fileType": filename.rsplit(".", 1)[-1].lower() if "." in filename else "txt",
                "mimeType": getattr(upload, "content_type", None) or "application/octet-stream",
                "storagePath": storage_path,
            }, uid)
            source_ids.append(source["id"])

        plan_payload = {
            "availability": course_payload.get("availability"),
            "availabilityWindows": course_payload.get("availabilityWindows"),
            "sessionMinutes": course_payload.get("sessionMinutes"),
            "preferredStartTime": course_payload.get("preferredStartTime"),
            "startDate": date.today().isoformat(),
        }
        background_tasks.add_task(
            svc.process_onboarding_course,
            pool,
            course_id,
            uid,
            syllabus_storage_path,
            syllabus_payload,
            source_ids,
            plan_payload,
        )
        sources = await svc.list_sources(pool, course_id, uid)
        return {
            "course": await svc.get_course(pool, course_id, uid),
            "processing": True,
            "syllabusStatus": "processing",
            "sourceCount": len(source_ids),
            "sources": sources,
        }
    except Exception as error:
        _raise(error)


@router.get("/api/courses/{course_id}")
async def get_course(course_id: str, user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    try:
        return await svc.get_course(pool, course_id, _uid(user_id))
    except Exception as error:
        _raise(error)


@router.get("/api/courses/{course_id}/chunks")
async def list_course_chunks(course_id: str, user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    try:
        return await svc.list_chunks(pool, course_id, _uid(user_id))
    except Exception as error:
        _raise(error)



@router.patch("/api/courses/{course_id}")
async def update_course(course_id: str, body: dict[str, Any], user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    try:
        return await svc.update_course(pool, course_id, body, _uid(user_id))
    except Exception as error:
        _raise(error)


@router.delete("/api/courses/{course_id}", status_code=204)
async def delete_course(course_id: str, user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    try:
        await svc.delete_course(pool, course_id, _uid(user_id))
        return Response(status_code=204)
    except Exception as error:
        _raise(error)


@router.get("/api/courses/{course_id}/sources")
async def list_sources(course_id: str, user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    return await svc.list_sources(pool, course_id, _uid(user_id))


@router.post("/api/courses/{course_id}/sources", status_code=201)
async def create_source(course_id: str, request: Request, user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    try:
        payload = await _source_payload_from_request(request)
        return await svc.create_source(pool, course_id, payload, _uid(user_id))
    except Exception as error:
        _raise(error)

@router.post("/api/courses/{course_id}/syllabus", status_code=201)
async def create_syllabus(course_id: str, request: Request, user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    payload: dict[str, Any] | None = None
    try:
        payload = await _syllabus_payload_from_request(request)
        return await svc.create_syllabus(pool, course_id, payload, _uid(user_id))
    except Exception as error:
        if payload and str(payload.get("mode") or payload.get("sourceType") or "").lower() in {"upload", "text"} and (payload.get("text") or payload.get("rawText")):
            return await svc.mark_uploaded_syllabus_parse_failed(pool, course_id, payload, error, _uid(user_id))
        _raise(error)

@router.get("/api/courses/{course_id}/syllabus")
async def get_syllabus(course_id: str, user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    try:
        return await svc.get_syllabus(pool, course_id, _uid(user_id))
    except Exception as error:
        _raise(error)


@router.post("/api/courses/{course_id}/syllabus/retry", status_code=201)
async def retry_uploaded_syllabus(course_id: str, user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    try:
        return await svc.retry_uploaded_syllabus(pool, course_id, _uid(user_id))
    except Exception as error:
        _raise(error)


@router.post("/api/courses/{course_id}/syllabus/from-sources", status_code=201)
async def create_syllabus_from_sources(course_id: str, user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    try:
        return await svc.create_syllabus_from_sources(pool, course_id, _uid(user_id))
    except Exception as error:
        _raise(error)


class ApproveSyllabusBody(BaseModel):
    lessons: list[dict[str, Any]]
    planPayload: dict[str, Any]
    generateQuizzes: bool = True


@router.post("/api/courses/{course_id}/approve-syllabus")
async def approve_syllabus(
    course_id: str,
    body: ApproveSyllabusBody,
    background_tasks: BackgroundTasks,
    user_id: str | None = None,
    pool: asyncpg.Pool = Depends(get_pool),
):
    try:
        return await svc.approve_syllabus(
            pool, course_id, body.lessons, body.planPayload, _uid(user_id), background_tasks, body.generateQuizzes
        )
    except Exception as error:
        _raise(error)

@router.patch("/api/courses/{course_id}/current-lesson")
async def update_current_lesson(course_id: str, body: dict[str, Any], user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    try:
        return await svc.update_current_lesson(pool, course_id, body, _uid(user_id))
    except Exception as error:
        _raise(error)

@router.post("/api/courses/{course_id}/map-syllabus")
async def map_syllabus(course_id: str, user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    try:
        return await svc.map_syllabus(pool, course_id, _uid(user_id))
    except Exception as error:
        _raise(error)

@router.post("/api/courses/{course_id}/diagnostic-test", status_code=201)
async def diagnostic_test(course_id: str, body: dict[str, Any] | None = None, user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    try:
        return await svc.generate_diagnostic_test(pool, course_id, body or {}, _uid(user_id))
    except Exception as error:
        _raise(error)


@router.patch("/api/sources/{source_id}")
async def update_source(source_id: str, body: dict[str, Any], user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    try:
        return await svc.update_source(pool, source_id, body, _uid(user_id))
    except Exception as error:
        _raise(error)


@router.delete("/api/sources/{source_id}", status_code=204)
async def delete_source(source_id: str, user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    await svc.delete_source(pool, source_id, _uid(user_id))
    return Response(status_code=204)


@router.post("/api/sources/{source_id}/parse")
async def parse_source(source_id: str, user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    try:
        return await svc.process_source(pool, source_id, _uid(user_id))
    except Exception as error:
        _raise(error)


@router.get("/api/courses/{course_id}/topics")
async def list_topics(course_id: str, user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    return await svc.list_topics(pool, course_id, _uid(user_id))


@router.post("/api/courses/{course_id}/self-assessment")
async def submit_self_assessment(course_id: str, body: dict[str, Any], user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    try:
        return await svc.submit_self_assessment(pool, course_id, body, _uid(user_id))
    except Exception as error:
        _raise(error)

@router.post("/api/courses/{course_id}/generate-topic-map")
async def generate_topic_map(course_id: str, user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    return await svc.generate_topic_map(pool, course_id, _uid(user_id))

@router.post("/api/courses/{course_id}/reindex-topics")
async def reindex_topics(course_id: str, body: dict[str, Any] | None = None, user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    try:
        return await svc.reindex_course_topics(pool, course_id, _uid(user_id), bool((body or {}).get("apply")))
    except Exception as error:
        _raise(error)


@router.post("/api/courses/{course_id}/generate-plan")
async def generate_course_plan(course_id: str, body: dict[str, Any] | None = None, user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    return await svc.generate_plan(pool, course_id, body or {}, _uid(user_id))


@router.get("/api/tasks")
async def list_tasks(request: Request, user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    return await svc.list_tasks(pool, dict(request.query_params), _uid(user_id))


@router.get("/api/tasks/today")
async def today_tasks(user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    tasks = await svc.list_tasks(pool, {}, _uid(user_id))
    return [task for task in tasks if task.get("startAt") and task["startAt"][:10] == date.today().isoformat()]


@router.post("/api/tasks", status_code=201)
async def create_task(body: dict[str, Any], user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    try:
        return await svc.create_task(pool, body, _uid(user_id))
    except Exception as error:
        _raise(error)


@router.patch("/api/tasks/{task_id}")
async def update_task(task_id: str, body: dict[str, Any], user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    try:
        return await svc.update_task(pool, task_id, body, _uid(user_id))
    except Exception as error:
        _raise(error)


@router.delete("/api/tasks/{task_id}", status_code=204)
async def delete_task(task_id: str, user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    await svc.delete_task(pool, task_id, _uid(user_id))
    return Response(status_code=204)


@router.get("/api/busy-events")
async def list_busy_events(request: Request, user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    try:
        return await svc.list_busy_events(pool, dict(request.query_params), _uid(user_id))
    except Exception as error:
        _raise(error)


@router.post("/api/busy-events", status_code=201)
async def create_busy_event(body: dict[str, Any], user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    try:
        return await svc.create_busy_event(pool, body, _uid(user_id))
    except Exception as error:
        _raise(error)


@router.patch("/api/busy-events/{event_id}")
async def update_busy_event(event_id: str, body: dict[str, Any], user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    try:
        return await svc.update_busy_event(pool, event_id, body, _uid(user_id))
    except Exception as error:
        _raise(error)


@router.delete("/api/busy-events/{event_id}", status_code=204)
async def delete_busy_event(event_id: str, delete_series: bool = False, user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    try:
        await svc.delete_busy_event(pool, event_id, _uid(user_id), delete_series)
        return Response(status_code=204)
    except Exception as error:
        _raise(error)


@router.post("/api/schedule/generate")
async def generate_schedule(body: dict[str, Any], user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    course_id = body.get("courseId")
    if not course_id:
        raise HTTPException(status_code=400, detail="courseId is required")
    return await svc.generate_plan(pool, course_id, body, _uid(user_id))


@router.post("/api/schedule/reschedule")
async def reschedule(body: dict[str, Any] | None = None, user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    return await svc.reschedule_missed(pool, body or {}, _uid(user_id))


@router.get("/api/courses/{course_id}/chat-threads")
async def list_chat_threads(course_id: str, user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    return await svc.list_chat_threads(pool, course_id, _uid(user_id))


@router.post("/api/chat-threads", status_code=201)
async def create_chat_thread(body: dict[str, Any], user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    try:
        return await svc.create_chat_thread(pool, body, _uid(user_id))
    except Exception as error:
        _raise(error)


@router.get("/api/chat-threads/{thread_id}/messages")
async def list_chat_messages(thread_id: str, user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    return await svc.list_chat_messages(pool, thread_id, _uid(user_id))


@router.delete("/api/chat-threads/{thread_id}", status_code=204)
async def delete_chat_thread(thread_id: str, user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    await svc.delete_chat_thread(pool, thread_id, _uid(user_id))
    return Response(status_code=204)


@router.post("/api/chat")
async def chat(body: dict[str, Any], user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    try:
        if "courseId" in body or "message" in body:
            return await svc.send_rag_chat(pool, body, _uid(user_id))
        return await svc.generic_chat(body)
    except Exception as error:
        _raise(error)


@router.post("/api/quizzes/generate", status_code=201)
async def generate_quiz(body: dict[str, Any], user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    try:
        return await svc.generate_quiz(pool, body, _uid(user_id))
    except Exception as error:
        _raise(error)


@router.get("/api/courses/{course_id}/quizzes")
async def list_quizzes(course_id: str, user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    return await svc.list_quizzes(pool, course_id, _uid(user_id))


@router.get("/api/quizzes/{quiz_id}")
async def get_quiz(quiz_id: str, user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    try:
        return await svc.get_quiz(pool, quiz_id, _uid(user_id))
    except Exception as error:
        _raise(error)


@router.post("/api/quiz-results", status_code=201)
async def create_quiz_result(body: dict[str, Any], user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    try:
        return await svc.create_quiz_result(pool, body, _uid(user_id))
    except Exception as error:
        _raise(error)


@router.get("/api/quiz-results/{result_id}")
async def get_quiz_result(result_id: str, user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    try:
        return await svc.get_quiz_result(pool, result_id, _uid(user_id))
    except Exception as error:
        _raise(error)


@router.post("/api/flashcards/generate", status_code=201)
async def generate_flashcards(body: dict[str, Any], user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    try:
        return await svc.generate_flashcards(pool, body, _uid(user_id))
    except Exception as error:
        _raise(error)


@router.get("/api/courses/{course_id}/flashcards")
async def list_flashcards(course_id: str, user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    return await svc.list_flashcards(pool, course_id, _uid(user_id))


@router.post("/api/flashcard-sessions", status_code=201)
async def create_flashcard_session(body: dict[str, Any], user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    try:
        return await svc.create_flashcard_session(pool, body, _uid(user_id))
    except Exception as error:
        _raise(error)


@router.patch("/api/flashcards/{flashcard_id}/review")
async def review_flashcard(flashcard_id: str, body: dict[str, Any], user_id: str | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    try:
        return await svc.review_flashcard(pool, flashcard_id, body.get("rating"), _uid(user_id))
    except Exception as error:
        _raise(error)


async def _source_payload_from_request(request: Request) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" not in content_type:
        return await request.json()

    form = await request.form()
    upload = form.get("file")
    payload = {key: value for key, value in form.multi_items() if key != "file"}
    if upload is None:
        return payload

    filename = getattr(upload, "filename", None) or "upload.txt"
    contents = await upload.read()
    log_upload_metadata(get_request_id(), filename, getattr(upload, "content_type", None), len(contents))
    storage_path = save_uploaded_file(filename, contents)
    try:
        text = extract_text_from_file_path(storage_path)
    except Exception:
        text = sanitize_text_for_postgres(contents.decode("utf-8", errors="ignore"))
    payload.update({
        "filename": filename,
        "originalName": filename,
        "fileType": filename.rsplit(".", 1)[-1].lower() if "." in filename else "txt",
        "mimeType": getattr(upload, "content_type", None) or "application/octet-stream",
        "storagePath": os.path.abspath(storage_path),
        "text": text,
    })
    return payload

def _json_form_value(value: Any, field_name: str) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be JSON")
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{field_name} must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{field_name} must be a JSON object")
    return parsed

async def _syllabus_payload_from_request(request: Request) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" not in content_type:
        return await request.json()
    form = await request.form()
    payload = {key: value for key, value in form.multi_items() if key != "file"}
    for key in ("classMeetings", "class_meetings", "lessons"):
        if isinstance(payload.get(key), str):
            try:
                payload[key] = json.loads(payload[key])
            except json.JSONDecodeError:
                pass
    upload = form.get("file")
    if upload is None:
        return payload
    filename = getattr(upload, "filename", None) or "syllabus.txt"
    contents = await upload.read()
    storage_path = save_uploaded_file(filename, contents)
    try:
        text = extract_text_from_file_path(storage_path)
    except Exception:
        text = sanitize_text_for_postgres(contents.decode("utf-8", errors="ignore"))
    finally:
        if os.path.exists(storage_path):
            try:
                os.remove(storage_path)
            except Exception:
                pass
    payload.update({"mode": payload.get("mode") or "upload", "filename": filename, "text": text})
    return payload
