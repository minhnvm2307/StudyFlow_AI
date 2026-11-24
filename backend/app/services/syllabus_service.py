from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.core.document.llm_section_split import complete_json
from app.core.rag.text import normalize_for_search

LLM_SYLLABUS_MIN_CHARS = 200
LLM_SYLLABUS_MAX_CHARS = 50000


def lessons_from_payload(payload: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    mode, lessons, _parsed = parse_syllabus_payload(payload)
    return mode, lessons


def parse_syllabus_payload(payload: dict[str, Any]) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    mode = str(payload.get("mode") or payload.get("sourceType") or "manual").lower()
    if mode == "skip":
        return mode, [], {"mode": mode, "extractionMode": "skip", "lessons": []}
    if mode == "system":
        count = _int_or_none(payload.get("lessonCount") or payload.get("lesson_count")) or 12
        lessons = system_template_lessons(max(1, min(24, count)))
        return mode, lessons, {"mode": mode, "extractionMode": "system", "lessons": lessons}
    manual = payload.get("lessons")
    if isinstance(manual, list) and manual:
        lessons = _dedupe_repeated_chapter_titles([_normalize_lesson(item, index) for index, item in enumerate(manual)])
        return mode, lessons, {"mode": mode, "extractionMode": "manual", "lessons": manual, "normalizedLessons": lessons}

    text = str(payload.get("text") or payload.get("rawText") or "").strip()
    if mode in {"upload", "text"} and text:
        llm_result = extract_syllabus_via_llm(text)
        lessons = [_normalize_lesson(item, index) for index, item in enumerate(llm_result.get("lessons") or []) if isinstance(item, dict)]
        lessons = _dedupe_repeated_chapter_titles([item for item in lessons if _usable_title(item.get("title"))])
        chapters = [_normalize_chapter(item, index) for index, item in enumerate(llm_result.get("chapters") or []) if isinstance(item, dict)]
        parsed = dict(llm_result)
        parsed["mode"] = mode
        parsed["extractionMode"] = "llm"
        parsed["normalizedLessons"] = lessons
        parsed["chapters"] = [item for item in chapters if item]
        return mode, lessons, parsed

    lessons = parse_lessons_from_text(text)
    return mode, lessons, {"mode": mode, "extractionMode": "heuristic", "lessons": lessons}


def extract_syllabus_via_llm(text: str) -> dict[str, Any] | None:
    prompt_text = text.strip()[:LLM_SYLLABUS_MAX_CHARS]
    if not prompt_text:
        return None
    last_error: Exception | None = None
    last_data: Any = None
    for attempt in range(2):
        try:
            if attempt == 0:
                data = _complete_syllabus_json(prompt_text)
            else:
                data = _repair_syllabus_json(prompt_text, last_data, last_error)
            parsed = _validate_llm_syllabus(data)
            parsed["repairAttempted"] = attempt > 0
            return parsed
        except Exception as exc:
            last_error = exc
            if "data" in locals():
                last_data = data
    raise ValueError(f"LLM syllabus extraction failed after 2 attempts: {last_error}")


def _complete_syllabus_json(prompt_text: str) -> dict[str, Any]:
    data = complete_json(
        "Extract university syllabi. Return one strict JSON object only.",
        _syllabus_json_prompt(prompt_text),
        0.05,
        max_tokens=4000,
    )
    if not isinstance(data, dict):
        raise ValueError("LLM returned non-object syllabus JSON")
    return data


def _repair_syllabus_json(prompt_text: str, previous: Any, error: Exception | None) -> dict[str, Any]:
    data = complete_json(
        "Repair syllabus extraction JSON. Return one strict JSON object only.",
        (
            "The previous syllabus extraction failed validation. Return a corrected JSON object in the exact schema.\n"
            f"Validation error: {error}\n"
            f"Previous JSON/data: {repr(previous)[:8000]}\n\n"
            "Use the source syllabus only to fill missing or truncated academic lesson/chapter items; do not invent policies as lessons.\n"
            f"Source syllabus:\n{prompt_text}"
        ),
        0.0,
        max_tokens=4000,
    )
    if not isinstance(data, dict):
        raise ValueError("LLM repair returned non-object syllabus JSON")
    return data


def _syllabus_json_prompt(prompt_text: str) -> str:
    return (
        "Use only explicit syllabus text. Preserve order. Do not invent items.\n"
        "Lesson = scheduled week/class/lecture/session/teaching-plan row.\n"
        "Subtopic = numbered section under a chapter; do not make it a lesson unless explicitly scheduled separately.\n"
        "If there is no timeline, create one lesson per chapter.\n"
        "Do NOT extract grading policies, course policies, attendance criteria, prerequisites, reference books, project instructions, exams, or meta sections as lessons/chapters.\n"
        "Every lesson needs non-empty title. Every chapter needs non-empty title.\n"
        "Return exactly this JSON shape, no markdown:\n"
        "{\"course\":{\"title\":string,\"code\":string,\"language\":string},"
        "\"lessons\":[{\"week_number\":number|null,\"lesson_number\":number|null,\"title\":string,\"chapter\":string|null,\"sections\":[string]}],"
        "\"chapters\":[{\"chapter_number\":number|null,\"title\":string,\"weeks\":[number],\"sections\":[string]}]}\n\n"
        f"Syllabus:\n{prompt_text}"
    )


def _validate_llm_syllabus(data: dict[str, Any]) -> dict[str, Any]:
    lessons_raw = data.get("lessons")
    if not isinstance(lessons_raw, list) or not lessons_raw:
        raise ValueError("LLM syllabus JSON must include non-empty lessons")
    lessons = []
    for index, item in enumerate(lessons_raw):
        if not isinstance(item, dict):
            continue
        title = _usable_title(item.get("title"))
        if not title:
            continue
        lesson = dict(item)
        lesson["title"] = title
        lesson["lesson_number"] = _int_or_none(lesson.get("lesson_number") or lesson.get("lesson")) or index + 1
        lesson["week_number"] = _int_or_none(lesson.get("week_number") or lesson.get("week")) or lesson["lesson_number"]
        sections = lesson.get("sections") or []
        lesson["sections"] = [str(section).strip() for section in sections if str(section).strip()] if isinstance(sections, list) else []
        lessons.append(lesson)
    if not lessons:
        raise ValueError("LLM syllabus JSON lessons have no usable titles")
    # Duplicate week numbers are allowed as multiple lessons/topics can be scheduled in the same week.

    chapters_raw = data.get("chapters") or []
    chapters = []
    if isinstance(chapters_raw, list):
        for index, item in enumerate(chapters_raw):
            if not isinstance(item, dict):
                continue
            title = _usable_title(item.get("title"))
            if not title:
                continue
            chapter = dict(item)
            chapter["title"] = title
            chapter["chapter_number"] = _int_or_none(chapter.get("chapter_number") or chapter.get("number")) or index + 1
            weeks_value = chapter.get("weeks") or chapter.get("coveredInWeeks") or []
            if isinstance(weeks_value, (str, int)):
                weeks_value = [weeks_value]
            chapter["weeks"] = [week for week in (_int_or_none(value) for value in weeks_value) if week is not None]
            sections = chapter.get("sections") or []
            chapter["sections"] = [str(section).strip() for section in sections if str(section).strip()] if isinstance(sections, list) else []
            chapters.append(chapter)

    course = data.get("course") if isinstance(data.get("course"), dict) else {}
    return {
        "courseTitle": _usable_title(course.get("title")) if isinstance(course, dict) else None,
        "courseCode": str(course.get("code") or "").strip() if isinstance(course, dict) else None,
        "sourceLanguage": str(course.get("language") or "").strip() if isinstance(course, dict) else None,
        "lessons": lessons,
        "chapters": chapters,
    }


def _parse_compact_syllabus_response(raw: str) -> dict[str, Any] | None:
    result: dict[str, Any] = {"courseTitle": None, "courseCode": None, "sourceLanguage": None, "lessons": [], "chapters": []}
    for line in raw.splitlines():
        line = line.strip().strip("`")
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in line.split("|")]
        kind = parts[0].upper() if parts else ""
        if kind == "COURSE" and len(parts) >= 4:
            result["courseTitle"] = parts[1] or None
            result["courseCode"] = parts[2] or None
            result["sourceLanguage"] = parts[3] or None
            continue
        if kind == "L" and len(parts) >= 6:
            sections = _split_compact_list(parts[5])
            title = _usable_title(parts[3]) or _usable_title(parts[4]) or (sections[0] if sections else "")
            if not title:
                continue
            result["lessons"].append(
                {
                    "week": _int_or_none(parts[1]),
                    "lesson": _int_or_none(parts[2]),
                    "title": title,
                    "chapter": parts[4] or None,
                    "sections": sections,
                }
            )
            continue
        if kind == "C" and len(parts) >= 5:
            title = _usable_title(parts[2])
            if not title:
                continue
            result["chapters"].append(
                {
                    "number": _int_or_none(parts[1]),
                    "title": title,
                    "weeks": [_int_or_none(value) for value in _split_compact_list(parts[3], separators=",;")],
                    "sections": _split_compact_list(parts[4]),
                }
            )
    result["lessons"] = [item for item in result["lessons"] if _usable_title(item.get("title"))]
    for chapter in result["chapters"]:
        chapter["weeks"] = [week for week in chapter.get("weeks", []) if week is not None]
    result["chapters"] = [item for item in result["chapters"] if _usable_title(item.get("title"))]
    if not result["lessons"] and result["chapters"]:
        result["lessons"] = _lessons_from_compact_chapters(result["chapters"])
    if result["lessons"] and not result["chapters"]:
        result["chapters"] = _chapters_from_compact_lessons(result["lessons"])
    if not result["lessons"]:
        return None
    return result


def _usable_title(value: Any) -> str:
    title = str(value or "").strip(" `\t\r\n")
    if not title or title.lower() in {"blank", "n/a", "na", "none", "null", "-", "--"}:
        return ""
    return title


def _lessons_from_compact_chapters(chapters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lessons = []
    for index, chapter in enumerate(chapters):
        weeks = chapter.get("weeks") or []
        lessons.append(
            {
                "week": weeks[0] if weeks else index + 1,
                "lesson": index + 1,
                "title": chapter["title"],
                "chapter": chapter["title"],
                "sections": chapter.get("sections") or [],
            }
        )
    return lessons


def _chapters_from_compact_lessons(lessons: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chapters_by_key: dict[str, dict[str, Any]] = {}
    for lesson in lessons:
        title = _usable_title(lesson.get("chapter")) or _infer_chapter_label(lesson.get("title"), *(lesson.get("sections") or [])) or _usable_title(lesson.get("title"))
        if not title:
            continue
        key = normalize_for_search(title)
        chapter = chapters_by_key.setdefault(key, {"number": len(chapters_by_key) + 1, "title": title, "weeks": [], "sections": []})
        if lesson.get("week") and lesson["week"] not in chapter["weeks"]:
            chapter["weeks"].append(lesson["week"])
        for section in lesson.get("sections") or []:
            if section not in chapter["sections"]:
                chapter["sections"].append(section)
    return list(chapters_by_key.values())


def _split_compact_list(value: str, separators: str = ";") -> list[str]:
    if not value.strip():
        return []
    pattern = "[" + re.escape(separators) + "]"
    return [item.strip() for item in re.split(pattern, value) if item.strip()]


def system_template_lessons(count: int = 12) -> list[dict[str, Any]]:
    return [
        _normalize_lesson(
            {
                "weekNumber": index + 1,
                "lessonNumber": index + 1,
                "title": f"Lesson {index + 1}",
                "description": "Template lesson. Rename or map this after adding the course syllabus.",
                "assignedReadings": [],
            },
            index,
        )
        for index in range(count)
    ]


def parse_lessons_from_text(text: str) -> list[dict[str, Any]]:
    if not text.strip():
        return []
    lines = [line.strip(" -\t") for line in text.splitlines() if line.strip()]
    numbered = _parse_numbered_syllabus_lines(lines)
    if numbered:
        return numbered

    lessons: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    pattern = re.compile(r"(?i)\b(?:week|wk|lesson|lecture|class|session|tuần|tuan|bài|bai|buổi|buoi)\s*(\d+)\b[:\-.\s]*(.*)")
    reading_pattern = re.compile(r"(?i)\b(?:reading|readings|required reading|chapter|chapters|section|sections|tài liệu đọc|tai lieu doc|chương|chuong)\b[:\-.\s]*(.*)")

    for line in lines:
        match = pattern.search(line)
        if match:
            if current:
                lessons.append(_normalize_lesson(current, len(lessons)))
            number = int(match.group(1))
            title = (match.group(2) or "").strip(" :-") or f"Lesson {number}"
            current = {
                "weekNumber": number if any(token in normalize_for_search(match.group(0)) for token in ("week", "wk", "tuan")) else None,
                "lessonNumber": number,
                "title": title,
                "description": line,
                "assignedReadings": [],
            }
            continue
        reading = reading_pattern.search(line)
        if current and reading:
            current.setdefault("assignedReadings", []).append(reading.group(1).strip() or line)
            continue
        if current:
            current["description"] = f"{current.get('description') or ''}\n{line}".strip()
        elif len(line) > 5:
            current = {"title": line, "description": line, "assignedReadings": []}

    if current:
        lessons.append(_normalize_lesson(current, len(lessons)))
    if lessons:
        return lessons
    chunks = [chunk.strip() for chunk in re.split(r"\n\s*\n", text) if chunk.strip()]
    return [_normalize_lesson({"title": chunk.splitlines()[0][:120], "description": chunk}, index) for index, chunk in enumerate(chunks[:12])]


def _parse_numbered_syllabus_lines(lines: list[str]) -> list[dict[str, Any]]:
    starts = [index for index, line in enumerate(lines) if _numbered_line_value(line) is not None]
    if len(starts) < 3:
        return []
    lessons: list[dict[str, Any]] = []
    current_number: int | None = None
    current_lines: list[str] = []
    for line in lines:
        number = _numbered_line_value(line)
        if number is not None:
            if current_number is not None and current_lines:
                lessons.append(_lesson_from_numbered_block(current_number, current_lines, len(lessons)))
            current_number = number
            current_lines = []
            continue
        if current_number is not None:
            current_lines.append(line)
    if current_number is not None and current_lines:
        lessons.append(_lesson_from_numbered_block(current_number, current_lines, len(lessons)))
    return lessons


def _numbered_line_value(line: str) -> int | None:
    direct = re.fullmatch(r"(?:(?:tuần|tuan)\s*)?(\d{1,2})", line.strip().lower())
    if direct:
        return int(direct.group(1))
    normalized = normalize_for_search(line)
    match = re.fullmatch(r"(?:tuan\s*)?(\d{1,2})", normalized)
    return int(match.group(1)) if match else None


def _lesson_from_numbered_block(number: int, lines: list[str], index: int) -> dict[str, Any]:
    description = "\n".join(lines).strip()
    title = lines[0].strip() if lines else f"Lesson {number}"
    return _normalize_lesson(
        {
            "weekNumber": number,
            "lessonNumber": number,
            "title": title,
            "description": description,
            "assignedReadings": _readings_from_lesson_text(description),
        },
        index,
    )


def _readings_from_lesson_text(text: str) -> list[str]:
    readings: list[str] = []
    for match in re.finditer(r"(?i)\b(?:chương|chuong|chapter)\s*([0-9ivxlcdm]+)", text):
        value = match.group(0).strip().rstrip(":.;")
        if value not in readings:
            readings.append(value)
    return readings


def _normalize_lesson(item: dict[str, Any], index: int) -> dict[str, Any]:
    week = _int_or_none(item.get("weekNumber") or item.get("week_number") or item.get("week"))
    lesson = _int_or_none(item.get("lessonNumber") or item.get("lesson_number") or item.get("lesson")) or index + 1
    title = str(item.get("title") or item.get("name") or f"Lesson {lesson}").strip()
    readings = item.get("assignedReadings") or item.get("assigned_readings") or item.get("readings") or []
    if isinstance(readings, str):
        readings = [readings]
    description = str(item.get("description") or item.get("summary") or title).strip()
    chapter = str(item.get("chapter") or "").strip() or _infer_chapter_label(title, description, *readings)
    if chapter and chapter not in readings:
        readings = [chapter, *readings]
    sections = item.get("sections") or []
    if isinstance(sections, str):
        sections = [sections]
    section_lines = [str(section).strip() for section in sections if str(section).strip()]
    missing_sections = [section for section in section_lines if section not in description]
    if missing_sections:
        description = f"{description}\n" + "\n".join(missing_sections)
    return {
        "week_number": week or lesson,
        "lesson_number": lesson,
        "title": title,
        "description": description,
        "assigned_readings": [str(value).strip() for value in readings if str(value).strip()],
        "sections": section_lines,
        "order_idx": int(item.get("orderIdx") or item.get("order_idx") or index),
    }


def _normalize_chapter(item: dict[str, Any], index: int) -> dict[str, Any] | None:
    number = _int_or_none(
        item.get("chapterNumber")
        or item.get("chapter_number")
        or item.get("number")
        or item.get("chapter")
    ) or index + 1
    title = str(item.get("title") or item.get("name") or "").strip()
    if not title:
        return None
    sections = item.get("sections") or item.get("subtopics") or []
    if isinstance(sections, str):
        sections = [sections]
    weeks = item.get("coveredInWeeks") or item.get("covered_in_weeks") or item.get("weeks") or []
    if isinstance(weeks, (str, int)):
        weeks = [weeks]
    return {
        "chapterNumber": number,
        "title": title,
        "sections": [str(section).strip() for section in sections if str(section).strip()],
        "coveredInWeeks": [week for week in (_int_or_none(value) for value in weeks) if week is not None],
    }


def _dedupe_repeated_chapter_titles(lessons: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_chapter: dict[str, list[dict[str, Any]]] = {}
    for lesson in lessons:
        chapter = _lesson_chapter(lesson)
        if chapter:
            by_chapter.setdefault(_normalize_identifier(chapter), []).append(lesson)
    for group in by_chapter.values():
        if len(group) < 2:
            continue
        for lesson in group:
            sections = [str(value).strip() for value in lesson.get("sections") or [] if str(value).strip()]
            detail = _section_title(sections[0]) if sections else ""
            if not detail:
                continue
            original = str(lesson.get("title") or "").strip()
            description = str(lesson.get("description") or "").strip()
            if original and original not in description:
                lesson["description"] = f"{original}\n{description}".strip()
            lesson["title"] = detail
    return lessons

def _lesson_chapter(lesson: dict[str, Any]) -> str:
    readings = lesson.get("assigned_readings") or lesson.get("assignedReadings") or []
    for reading in readings:
        text = str(reading or "").strip()
        if re.search(r"(?i)\b(?:chương|chuong|chapter)\s+[0-9ivxlcdm]+\b", text):
            return text
    return _infer_chapter_label(lesson.get("title"), lesson.get("description"))

def _section_title(section: str) -> str:
    return re.sub(r"^\s*\d+(?:\.\d+)*\s*[.)-]?\s*", "", str(section or "")).strip()


def _infer_chapter_label(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        match = re.search(r"(?i)\b(?:chÆ°Æ¡ng|chuong|chapter)\s+[0-9ivxlcdm]+\b", text)
        if match:
            return match.group(0).strip().rstrip(":.;,-")
    return ""


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def _chapter_labels_from_text(text: str) -> list[str]:
    folded = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii").lower()
    if not folded:
        return []
    labels: list[str] = []
    for match in re.finditer(r"\b(chuong|chapter)\s*([0-9ivxlcdm]+)\b", folded):
        prefix = "Chapter" if match.group(1) == "chapter" else "Chuong"
        number = match.group(2)
        value = f"{prefix} {number.upper() if number.isalpha() else number}"
        if value not in labels:
            labels.append(value)
    return labels


def _readings_from_lesson_text(text: str) -> list[str]:
    return _chapter_labels_from_text(text)


def _infer_chapter_label(*values: Any) -> str:
    for value in values:
        labels = _chapter_labels_from_text(str(value or ""))
        if labels:
            return labels[0]
    return ""


def _lesson_chapter(lesson: dict[str, Any]) -> str:
    readings = lesson.get("assigned_readings") or lesson.get("assignedReadings") or []
    for reading in readings:
        chapter = _infer_chapter_label(reading)
        if chapter:
            return chapter
    return _infer_chapter_label(lesson.get("title"), lesson.get("description"))


def score_lesson_match(lesson: dict[str, Any], text: str) -> tuple[float, str]:
    haystack = normalize_for_search(text or "")
    if not haystack:
        return 0.0, "No searchable text."
    terms = []
    terms.extend(_keywords(str(lesson.get("title") or "")))
    terms.extend(_keywords(str(lesson.get("description") or "")))
    for reading in lesson.get("assigned_readings") or lesson.get("assignedReadings") or []:
        terms.extend(_keywords(str(reading)))
    terms = list(dict.fromkeys([term for term in terms if len(term) >= 4]))[:16]
    if not terms:
        return 0.0, "No lesson keywords."
    hits = [term for term in terms if term in haystack]
    score = len(hits) / max(1, len(terms))
    if hits and any(term in haystack for term in _keywords(str(lesson.get("title") or ""))):
        score += 0.25
    id_haystack = _normalize_identifier(text or "")
    readings = [_normalize_identifier(str(value)) for value in lesson.get("assigned_readings") or lesson.get("assignedReadings") or []]
    chapter_readings = [value for value in readings if re.search(r"\b(?:chuong|chapter)\s+[0-9ivxlcdm]+\b", value)]
    if any(value and value in id_haystack for value in chapter_readings):
        score += 0.25
    elif chapter_readings:
        score -= 0.2
    lesson_section_ids = set(re.findall(r"\b\d+(?:\.\d+)+\b", f"{lesson.get('title') or ''} {lesson.get('description') or ''} {' '.join(str(value) for value in lesson.get('assigned_readings') or [])}"))
    text_section_ids = set(re.findall(r"\b\d+(?:\.\d+)+\b", text or ""))
    if lesson_section_ids and text_section_ids:
        if lesson_section_ids & text_section_ids:
            score += 0.35
        else:
            score -= 0.15
    return max(0.0, min(1.0, score)), f"Matched: {', '.join(hits[:6])}" if hits else "No strong keyword overlap."


def _keywords(text: str) -> list[str]:
    normalized = normalize_for_search(text)
    stop = {"week", "lesson", "lecture", "class", "session", "chapter", "section", "required", "reading", "topic", "and", "the", "with", "from"}
    return [token for token in re.findall(r"[a-z0-9][a-z0-9_\-]{2,}", normalized) if token not in stop]


def _normalize_identifier(value: str) -> str:
    text = str(value or "").lower().replace("đ", "d")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text)).strip()
