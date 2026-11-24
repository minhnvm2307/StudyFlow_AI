from __future__ import annotations

import re
import unicodedata


def normalize_text(value: str | None) -> str:
    text = str(value or "").replace("\r", "")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{4,}", "\n\n", text)
    return text.strip()


def normalize_for_search(value: str | None) -> str:
    text = str(value or "").lower().replace("đ", "d").replace("Đ", "d")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    words = re.findall(r"[a-z0-9_]+", text)
    return " ".join(words)


def token_approx(value: str | None) -> int:
    return max(1, len(str(value or "")) // 4)


def extract_page_query(value: str | None) -> int | None:
    match = re.search(r"\b(?:page|trang)\s*(?:so\s*)?(\d{1,4})\b", str(value or ""), re.I)
    return int(match.group(1)) if match else None
