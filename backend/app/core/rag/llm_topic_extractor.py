from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from typing import Any

from app.config import settings
from app.core.document.llm_section_split import complete_json
from app.core.rag.pipeline import SectionBlock
from app.core.rag.text import normalize_for_search


class TopicExtractionError(RuntimeError):
    pass


def extract_topics_via_llm(
    subject_id: str,
    user_id: str,
    source: dict[str, Any],
    sections: list[SectionBlock],
    existing_count: int = 0,
) -> list[dict[str, Any]]:
    chapters = _chapter_samples(sections)
    if not chapters:
        raise TopicExtractionError("No readable sections for topic extraction.")

    data = complete_json(
        "You extract study topics from course materials. Return JSON only.",
        _prompt(source, chapters),
        0.15,
    )
    raw_topics = data.get("topics") if isinstance(data, dict) else None
    if not isinstance(raw_topics, list) or not raw_topics:
        raise TopicExtractionError("LLM returned no topics.")

    topics: list[dict[str, Any]] = []
    seen: set[str] = set()
    max_topics = max(1, settings.LLM_TOPICS_MAX_PER_SOURCE)
    for item in raw_topics:
        if not isinstance(item, dict):
            continue
        title = _clean_title(item.get("title") or item.get("topicName") or item.get("name"))
        if not title:
            continue
        chapter = _clean_title(item.get("chapterTitle") or item.get("chapter") or item.get("moduleName"))
        key = normalize_for_search(f"{chapter} {title}")
        if not key or key in seen:
            continue
        seen.add(key)
        order = existing_count + len(topics) + 1
        topic_id = f"topic-{subject_id}-{source['id']}-{hashlib.sha1(key.encode()).hexdigest()[:10]}"
        description = _clean_sentence(item.get("description") or item.get("summary") or "")
        content = _clean_sentence(item.get("contentSummary") or item.get("content_chunk") or description or title)
        keywords = _clean_keywords(item.get("keywords"))
        topics.append({
            "id": topic_id,
            "subject_id": subject_id,
            "user_id": user_id,
            "title": title[:120],
            "description": description[:500],
            "section_number": order,
            "content_chunk": content[:3000],
            "chapter_title": chapter,
            "keywords": keywords,
            "order_idx": order,
            "cost_mins": 30,
            "mastery": 0.05,
            "p_l0": 0.05,
            "p_t": 0.2,
            "p_g": 0.2,
            "p_s": 0.1,
            "awaiting_diagnostic": True,
            "fsrs_card": {},
            "fsrs_stability": 0.0,
            "fsrs_difficulty": 5.0,
            "fsrs_last_review": None,
            "fsrs_due_date": None,
            "merged_from": [],
            "is_learned": False,
        })
        if len(topics) >= max_topics:
            break

    if not topics:
        raise TopicExtractionError("LLM topics were invalid after normalization.")
    return topics


def _chapter_samples(sections: list[SectionBlock]) -> list[dict[str, Any]]:
    grouped: dict[str, list[SectionBlock]] = defaultdict(list)
    for section in sections:
        grouped[section.chapter_title or section.section_title or "General"].append(section)

    chapters = []
    for chapter, items in grouped.items():
        text_parts = []
        for section in items:
            text_parts.append(f"[{section.section_title}]\n{section.text}")
        sample = "\n\n".join(text_parts)
        chapters.append({
            "chapterTitle": chapter,
            "pageStart": next((item.page_start for item in items if item.page_start is not None), None),
            "pageEnd": next((item.page_end for item in reversed(items) if item.page_end is not None), None),
            "text": sample[: settings.LLM_TOPIC_CHARS_PER_CHAPTER],
        })
    return chapters


def _prompt(source: dict[str, Any], chapters: list[dict[str, Any]]) -> str:
    max_per_chapter = max(1, settings.LLM_TOPICS_MAX_PER_CHAPTER)
    chapter_text = "\n\n---\n\n".join(
        f"Chapter: {chapter['chapterTitle']}\nPages: {chapter.get('pageStart') or 'n/a'}-{chapter.get('pageEnd') or 'n/a'}\nText:\n{chapter['text']}"
        for chapter in chapters
    )
    return f"""
Extract study topics from this course document.

Rules:
- Use only the document text below. Do not invent syllabus items.
- Return topics in the document language.
- Extract up to {max_per_chapter} focused study topics per chapter.
- A topic should be useful for a 30-45 minute study/review session.
- Avoid generic titles such as General, Page, Trang, Overview, Introduction unless the document genuinely teaches that concept.

Return exactly this JSON object:
{{
  "topics": [
    {{
      "title": "specific study topic",
      "description": "one-sentence grounded description",
      "chapterTitle": "chapter heading from the document",
      "pageStart": 1,
      "pageEnd": 10,
      "keywords": ["keyword"],
      "contentSummary": "short source-grounded summary for quiz generation"
    }}
  ]
}}

Document: {source.get('originalName') or source.get('filename') or source.get('id')}

{chapter_text}
""".strip()


def _clean_title(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip(" .:-")
    if not text:
        return ""
    if normalize_for_search(text) in {"general", "overview", "page", "trang"}:
        return ""
    return text


def _clean_sentence(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _clean_keywords(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        keyword = _clean_sentence(item)
        if keyword and normalize_for_search(keyword) not in {"page", "trang", "general"}:
            out.append(keyword[:80])
    return list(dict.fromkeys(out))[:12]
