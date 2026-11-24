from __future__ import annotations

import sys
from pathlib import Path


TESTS_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = TESTS_ROOT.parent
if str(TESTS_ROOT) not in sys.path:
    sys.path.insert(0, str(TESTS_ROOT))
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from evals import rag_seed


def test_load_tthcm_seed_payload_reads_real_docs():
    payload = rag_seed.load_tthcm_seed_payload()

    assert payload["subject_name"] == "Tư tưởng Hồ Chí Minh"
    assert "Khái niệm tư tưởng Hồ Chí Minh" in payload["syllabus_text"]
    assert "Tư tưởng Hồ Chí Minh là một hệ thống quan điểm toàn diện và sâu sắc" in payload["material_text"]
    assert len(payload["chunks"]) >= 3
    assert any("Chương 1" in chapter["title"] for chapter in payload["chapters"])
    assert any("Chương 6" in chapter["title"] for chapter in payload["chapters"])
