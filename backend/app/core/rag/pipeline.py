from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from app.core.rag.text import normalize_for_search, normalize_text, token_approx


@dataclass
class PageBlock:
    page: int | None
    text: str


@dataclass
class SectionBlock:
    section_id: str
    section_path: str
    section_title: str
    section_level: str
    chapter_title: str
    page_start: int | None
    page_end: int | None
    text: str


def parse_pages(text: str) -> list[PageBlock]:
    clean = normalize_text(text)
    marker = re.compile(r"^\s*(?:page|trang)\s+(\d{1,4})\s*$", re.I | re.M)
    matches = list(marker.finditer(clean))
    if not matches:
        return [PageBlock(page=None, text=clean)] if clean else []

    pages: list[PageBlock] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(clean)
        body = clean[start:end].strip()
        if body:
            pages.append(PageBlock(page=int(match.group(1)), text=body))
    return pages


def build_sections(source_id: str, pages: list[PageBlock]) -> list[SectionBlock]:
    sections: list[SectionBlock] = []
    current_title = "General"
    current_path = "General"
    current_level = "section"
    current_chapter = "General"
    current_lines: list[str] = []
    current_page: int | None = pages[0].page if pages else None
    current_page_end: int | None = current_page
    section_index = 0
    path: list[str] = []

    def flush() -> None:
        nonlocal section_index, current_lines
        text = normalize_text("\n".join(current_lines))
        if not text:
            current_lines = []
            return
        section_index += 1
        sections.append(SectionBlock(
            section_id=f"sec_{source_id}_{section_index:04d}",
            section_path=current_path,
            section_title=current_title,
            section_level=current_level,
            chapter_title=current_chapter,
            page_start=current_page,
            page_end=current_page_end or current_page,
            text=text,
        ))
        current_lines = []

    for page in pages:
        for raw_line in page.text.splitlines():
            line = raw_line.strip()
            heading = detect_heading(line)
            if heading:
                flush()
                title, level = heading
                if level == "chapter":
                    path[:] = [title]
                elif level == "section":
                    if not path:
                        path[:] = [title]
                    elif _is_numeric_heading(title) and len(path) >= 2 and _is_roman_heading(path[-1]):
                        path[2:] = [title]
                    else:
                        path[1:] = [title]
                else:
                    if len(path) < 2:
                        path.append(title)
                    else:
                        path[2:] = [title]
                current_title = title
                current_path = " > ".join(path) or title
                current_level = level
                current_chapter = path[0] if path else title
                current_page = page.page
                current_page_end = page.page
                continue
            current_page = current_page if current_lines else page.page
            current_page_end = page.page or current_page_end
            current_lines.append(raw_line)
    flush()

    if not sections and pages:
        joined = "\n\n".join(page.text for page in pages)
        sections.append(SectionBlock(
            section_id=f"sec_{source_id}_0001",
            section_path="General",
            section_title="General",
            section_level="section",
            chapter_title="General",
            page_start=pages[0].page,
            page_end=pages[-1].page,
            text=joined,
        ))
    return sections


def semantic_chunk_split(text: str, max_chars: int = 1500, min_chars: int = 200) -> list[str]:
    # 1. Tách văn bản thành các đoạn lớn (Paragraphs)
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return [text] if text.strip() else []
        
    chunks = []
    current_chunk = []
    current_len = 0
    
    for p in paragraphs:
        # Nếu một đoạn quá dài so với giới hạn, phân rã đoạn đó theo câu
        if len(p) > max_chars:
            sentence_ends = re.compile(r"(?<=[.!?])\s+")
            sentences = [s.strip() for s in sentence_ends.split(p) if s.strip()]
            for s in sentences:
                if current_len + len(s) + 1 > max_chars and current_len >= min_chars:
                    chunks.append(" ".join(current_chunk))
                    current_chunk = [s]
                    current_len = len(s)
                else:
                    current_chunk.append(s)
                    current_len += len(s) + 1
        else:
            if current_len + len(p) + 2 > max_chars and current_len >= min_chars:
                chunks.append("\n\n".join(current_chunk))
                current_chunk = [p]
                current_len = len(p)
            else:
                current_chunk.append(p)
                current_len += len(p) + 2
                
    if current_chunk:
        chunks.append("\n\n".join(current_chunk))
        
    return chunks



def create_chunks(subject_id: str, source: dict[str, Any], sections: list[SectionBlock], size: int = 900) -> list[dict[str, Any]]:
    from app.core.rag.embedding import get_embedding
    
    chunks: list[dict[str, Any]] = []
    chunk_index = 0
    for section in sections:
        text = normalize_text(section.text)
        if not text:
            continue
            
        # 1. Structure-based check: if section is small, keep as single chunk
        if len(text) <= 1500:
            sub_chunks = [text]
        else:
            # 2. Try splitting by sub-headings/lists H3/H4 if present
            markers = [m for m in re.finditer(r"\n\s*(?:[a-z]\)|\d+(?:\.\d+){2,4}|[-*•])\s+", text)]
            if len(markers) >= 2:
                sub_parts = []
                last_idx = 0
                for m in markers:
                    part = text[last_idx:m.start()].strip()
                    if part:
                        sub_parts.append(part)
                    last_idx = m.start()
                part = text[last_idx:].strip()
                if part:
                    sub_parts.append(part)
                
                # Check if any sub-part is still too big; if so, split semantically
                sub_chunks = []
                for part in sub_parts:
                    if len(part) > 1800:
                        sub_chunks.extend(semantic_chunk_split(part))
                    else:
                        sub_chunks.append(part)
            else:
                # 3. Fallback: Semantic chunking split
                sub_chunks = semantic_chunk_split(text)
                
        for chunk_text in sub_chunks:
            chunk_text = chunk_text.strip()
            if not chunk_text:
                continue
            chunk_index += 1
            normalized = normalize_for_search(chunk_text)
            chunk_id = f"chunk_{source['id']}_{chunk_index:04d}"
            
            # Generate vector embedding (API call or offline pseudo-hash vector fallback)
            embedding_vector = get_embedding(chunk_text)
            
            chunks.append({
                "id": chunk_id,
                "chunkId": chunk_id,
                "courseId": subject_id,
                "documentId": source["id"],
                "sourceId": source["id"],
                "filename": source.get("originalName") or source.get("filename") or "source.txt",
                "chunkIndex": chunk_index,
                "text": chunk_text,
                "normalizedText": normalized,
                "quote": re.sub(r"\s+", " ", chunk_text)[:240],
                "page": section.page_start,
                "pageStart": section.page_start,
                "pageEnd": section.page_end or section.page_start,
                "sectionPath": section.section_path,
                "sectionTitle": section.section_title,
                "sectionLevel": section.section_level,
                "chapterName": section.section_path,
                "chapterTitle": section.chapter_title,
                "topicName": section.section_title,
                "topicIds": [],
                "contentHash": hashlib.sha256(f"{normalized}:{source['id']}".encode()).hexdigest(),
                "tokenCount": token_approx(chunk_text),
                "embeddingStatus": "ready",
                "embedding": embedding_vector,
            })
    return chunks



def extract_topics(subject_id: str, user_id: str, chunks: list[dict[str, Any]], existing_count: int = 0) -> list[dict[str, Any]]:
    topics: list[dict[str, Any]] = []
    seen: set[str] = set()
    for chunk in chunks:
        match = re.search(r"\btopic\s*:\s*([^\n.]{3,90})", chunk["text"], re.I)
        title = match.group(1).strip() if match else (chunk.get("topicName") or chunk.get("sectionTitle") or "").strip()
        if not title or title.lower() == "general":
            title = _title_from_text(chunk["text"])
        key = normalize_for_search(title)
        if not key or key in seen:
            continue
        seen.add(key)
        order = existing_count + len(topics) + 1
        topic_id = f"topic-{subject_id}-{hashlib.sha1(key.encode()).hexdigest()[:10]}"
        topics.append({
            "id": topic_id,
            "subject_id": subject_id,
            "user_id": user_id,
            "title": title[:120],
            "description": re.sub(r"\s+", " ", chunk["text"])[:240],
            "section_number": order,
            "content_chunk": chunk["text"][:3000],
            "chapter_title": chunk.get("chapterTitle") or chunk.get("sectionPath") or "",
            "keywords": [],
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
    return topics[:12]


def assign_topics_to_chunks(chunks: list[dict[str, Any]], topics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not chunks or not topics:
        return chunks
    topic_terms = [(_topic_search_terms(topic), topic) for topic in topics]
    for chunk in chunks:
        chunk_chapter = normalize_for_search(chunk.get("chapterTitle") or chunk.get("sectionPath") or "")
        haystack = normalize_for_search(" ".join([
            str(chunk.get("sectionPath") or ""),
            str(chunk.get("sectionTitle") or ""),
            str(chunk.get("text") or ""),
        ]))
        scored: list[tuple[float, str]] = []
        for terms, topic in topic_terms:
            topic_id = topic.get("id")
            if not topic_id:
                continue
            score = 0.0
            topic_chapter = normalize_for_search(topic.get("chapter_title") or topic.get("chapterTitle") or "")
            if topic_chapter and chunk_chapter and (topic_chapter in chunk_chapter or chunk_chapter in topic_chapter):
                score += 12.0
            for term in terms:
                if term and term in haystack:
                    score += 3.0 if len(term) > 4 else 1.0
            if score > 0:
                scored.append((score, topic_id))
        scored.sort(key=lambda item: item[0], reverse=True)
        if scored:
            chunk["topicIds"] = [topic_id for _score, topic_id in scored[:3]]
            continue
        same_chapter = [topic for _terms, topic in topic_terms if normalize_for_search(topic.get("chapter_title") or topic.get("chapterTitle") or "") == chunk_chapter]
        chunk["topicIds"] = [same_chapter[0]["id"]] if same_chapter else []
    return chunks


def detect_heading(line: str) -> tuple[str, str] | None:
    text = re.sub(r"\s+", " ", str(line or "").strip())
    if not text or len(text) > 160:
        return None
    normalized = normalize_for_search(text)
    if not normalized or normalized in {"trang", "page"}:
        return None

    hash_match = re.match(r"^(#{1,4})\s+\S", text)
    if hash_match:
        hashes = len(hash_match.group(1))
        return text.lstrip("# ").strip(), "chapter" if hashes == 1 else "section" if hashes == 2 else "subsection"

    chapter_patterns = [
        r"^(?:chapter|chuong|chương)\s+([ivxlcdm]+|\d{1,3})(?:\b|\s*[:.\-]).*",
        r"^(?:part|phan|phần)\s+([ivxlcdm]+|\d{1,3})(?:\b|\s*[:.\-]).*",
        r"^(?:unit|module|bai|bài)\s+([ivxlcdm]+|\d{1,3})(?:\b|\s*[:.\-]).*",
    ]
    if any(re.match(pattern, text, re.I) for pattern in chapter_patterns):
        return text.strip(" :"), "chapter"

    if re.match(r"^\d{1,2}\s*[-.)]?\s+\S", text) and not re.match(r"^\d{1,2}\.\d+", text):
        return text.strip(" :"), "chapter"

    if re.match(r"^[IVXLCDM]{1,8}\s*[-.)]\s+\S", text):
        return text.strip(" :"), "section"
    if re.match(r"^\d{1,2}(?:\.\d{1,2}){0,3}\s*[-.)]?\s+\S", text):
        return text.strip(" :"), "section"
    if re.match(r"^[a-zA-Z]\)\s+\S", text):
        return text.strip(" :"), "subsection"
    if re.match(r"^(?:topic|section)\s*:\s*\S", text, re.I):
        return re.sub(r"^(?:topic|section)\s*:\s*", "", text, flags=re.I).strip(" :"), "section"
    return None


def _topic_search_terms(topic: dict[str, Any]) -> list[str]:
    values = [topic.get("title"), topic.get("chapter_title"), topic.get("chapterTitle"), topic.get("description")]
    values.extend(topic.get("keywords") or [])
    terms: list[str] = []
    for value in values:
        normalized = normalize_for_search(value)
        if normalized:
            terms.append(normalized)
            terms.extend(term for term in normalized.split() if len(term) >= 4)
    return list(dict.fromkeys(terms))[:24]


def _is_roman_heading(title: str) -> bool:
    return bool(re.match(r"^[IVXLCDM]{1,8}\s*[-.)]\s+", title or ""))


def _is_numeric_heading(title: str) -> bool:
    return bool(re.match(r"^\d{1,2}(?:\.\d{1,2}){0,3}\s*[-.)]?\s+", title or ""))


def _find_chunk_end(text: str, start: int, size: int) -> int:
    target = min(start + size, len(text))
    if target >= len(text):
        return len(text)
    window_start = start + max(200, int(size * 0.55))
    slice_text = text[window_start:target]
    sentence = list(re.finditer(r"[.!?]\s+", slice_text))
    if sentence:
        return window_start + sentence[-1].start() + 1
    newline = text.rfind("\n", window_start, target)
    if newline > window_start:
        return newline
    space = text.rfind(" ", window_start, target)
    return space if space > window_start else target


def _next_offset(text: str, start: int, end: int) -> int:
    if end >= len(text):
        return end
    overlap = min(240, max(0, (end - start) // 4))
    return max(start + 1, end - overlap)


def _title_from_text(text: str) -> str:
    words = re.findall(r"[A-Za-zÀ-ỹ0-9][A-Za-zÀ-ỹ0-9\-]{2,}", text)
    return " ".join(words[:6]) or "General Concept"
