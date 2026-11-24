"""Document upload pipeline: extract → LLM split → merge → save → plan_dirty."""
from __future__ import annotations

import uuid

import asyncpg
import fsrs

from app.config import settings
from app.core.document.extractor import extract_text_from_file_path, save_uploaded_file
from app.core.document.llm_section_split import split_document_to_sections_via_llm
from app.core.document.merge import cap_max_sections, find_merge_candidate, merge_topic_content
from app.core.scheduler.bkt import BKTModel
from app.db import repository
from app.schemas.topic import Topic


async def handle_upload(
    pool: asyncpg.Pool,
    user_id: str,
    subject_id: str,
    file_name: str,
    raw_text: str,
) -> dict:
    """Returns {"subject": ..., "topics": [...], "tasks": [...]}"""
    # Check if a syllabus exists for this subject
    async with pool.acquire() as conn:
        syllabus = await conn.fetchrow(
            """SELECT id FROM course_syllabi
               WHERE subject_id=$1 AND user_id=$2 AND status <> 'skipped'
               ORDER BY created_at DESC LIMIT 1""",
            subject_id,
            user_id,
        )

    if syllabus is not None:
        from app.services.course_api_service import create_source
        payload = {
            "filename": file_name,
            "text": raw_text,
        }
        await create_source(pool, subject_id, payload, user_id)
        subject = await repository.get_subject(pool, subject_id)
        topics_out = await repository.get_topics(pool, subject_id)
        return {
            "subject": subject.model_dump() if subject else None,
            "topics": [t.model_dump() for t in topics_out],
            "tasks": [],
        }

    if len(raw_text) < settings.LOW_INFO_DOC_CHAR_THRESHOLD:
        new_topics = [Topic(
            id=f"topic-{subject_id}-{uuid.uuid4().hex[:8]}",
            subject_id=subject_id,
            user_id=user_id,
            title=f"General Concept: {file_name}",
            content_chunk=raw_text,
            mastery=BKTModel.DIAGNOSTIC_PRIORS["p_l0"],
            p_l0=BKTModel.DIAGNOSTIC_PRIORS["p_l0"],
            p_t=BKTModel.DIAGNOSTIC_PRIORS["p_t"],
            p_g=BKTModel.DIAGNOSTIC_PRIORS["p_g"],
            p_s=BKTModel.DIAGNOSTIC_PRIORS["p_s"],
            awaiting_diagnostic=True,
            fsrs_card={**fsrs.Card().to_dict(), "difficulty": 8.5, "stability": 0.5},
        )]
    else:
        new_topics = split_document_to_sections_via_llm(raw_text, subject_id)
        for t in new_topics:
            t.user_id = user_id

    existing = await repository.get_topics(pool, subject_id)
    original_existing_ids = {t.id for t in existing}
    existing_ids = set(original_existing_ids)
    truly_new = []

    for nt in new_topics:
        match = find_merge_candidate(nt.content_chunk, existing)
        if match:
            merge_topic_content(match, nt.content_chunk, nt.id)
        else:
            original_id = nt.id
            idx = 1
            while nt.id in existing_ids:
                nt.id = f"{original_id}-{idx}"
                idx += 1
            existing.append(nt)
            existing_ids.add(nt.id)
            truly_new.append(nt)

    # Assign order_idx to truly new topics
    max_order = max((t.order_idx for t in existing), default=0)
    for i, t in enumerate(truly_new):
        t.order_idx = max_order + i + 1

    existing, _ = cap_max_sections(existing, [])
    await repository.save_topics(pool, existing)
    await repository.set_plan_dirty(pool, user_id, True)

    subject = await repository.get_subject(pool, subject_id)
    topics_out = await repository.get_topics(pool, subject_id)

    return {
        "subject": subject.model_dump() if subject else None,
        "topics": [t.model_dump() for t in topics_out],
        "tasks": [],
    }
