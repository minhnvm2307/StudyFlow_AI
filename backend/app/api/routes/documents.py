import os
import uuid

import asyncpg
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from app.api.deps import current_user_id
from app.core.document.extractor import extract_text_from_file_path, save_uploaded_file, upload_file_to_s3
from app.db import repository
from app.db.pg_pool import get_pool
from app.services.document_service import handle_upload

router = APIRouter()


@router.post("/api/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    subject_id: str | None = Form(None),
    subject_id_query: str | None = Query(None, alias="subject_id"),
    user_id: str | None = Form(None),
    user_id_query: str | None = Query(None, alias="user_id"),
    pool: asyncpg.Pool = Depends(get_pool),
):
    del user_id, user_id_query
    uid = current_user_id()
    sid = subject_id or subject_id_query
    if not sid:
        subjects = await repository.get_subjects(pool, uid)
        if not subjects:
            raise HTTPException(404, "No subject found")
        sid = next(iter(subjects))

    subject = await repository.get_subject(pool, sid)
    if not subject:
        raise HTTPException(404, f"Subject '{sid}' not found.")

    contents = await file.read()
    file_path = save_uploaded_file(file.filename or "upload.pdf", contents)
    try:
        text = extract_text_from_file_path(file_path)
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

    result = await handle_upload(pool, uid, sid, file.filename or "upload.pdf", text)
    safe_name = "".join(char for char in file.filename if char.isalnum() or char in (".", "_", "-")).strip()
    s3_key = f"documents/{uid}/{sid}/{uuid.uuid4().hex[:8]}_{safe_name}"
    s3_url = upload_file_to_s3(contents, s3_key)
    return {"status": "success", "s3_url": s3_url, **result}


@router.post("/api/documents/mock-upload")
async def mock_upload(
    subject_id: str | None = Query(None),
    user_id: str | None = Query(None),
    pool: asyncpg.Pool = Depends(get_pool),
):
    uid = user_id or "user-demo"
    if not subject_id:
        subjects = await repository.get_subjects(pool, uid)
        if not subjects:
            raise HTTPException(404, "No subject found")
        subject_id = next(iter(subjects))

    subject = await repository.get_subject(pool, subject_id)
    if not subject:
        raise HTTPException(404, f"Subject '{subject_id}' not found.")

    result = await handle_upload(pool, uid, subject_id, "mock_document.pdf", "Mock document content for testing.")
    from app.services.unified_scheduler import build_unified_schedule

    await build_unified_schedule(pool, uid)
    return {"status": "success", **result}
