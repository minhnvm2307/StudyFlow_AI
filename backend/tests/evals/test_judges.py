import sys
from pathlib import Path

import pytest

TESTS_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = TESTS_ROOT.parent
if str(TESTS_ROOT) not in sys.path:
    sys.path.insert(0, str(TESTS_ROOT))
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from evals import judges


class _FakeResult:
    def __init__(self, value: float, reason: str):
        self.value = value
        self.reason = reason


@pytest.mark.anyio
async def test_evaluate_answer_relevance_uses_vietnamese_generation_and_embeddings(monkeypatch):
    calls: dict[str, object] = {}

    class FakeOutput:
        cau_hoi_suy_ra = "Khái niệm tư tưởng Hồ Chí Minh là gì?"
        khong_cam_ket = False
        ly_do = "Câu trả lời bám sát câu hỏi gốc."

    class FakeLLM:
        async def agenerate(self, prompt, output_model):
            calls["prompt"] = prompt
            calls["output_model"] = output_model
            return FakeOutput()

    class FakeEmbeddings:
        async def aembed_text(self, text):
            calls.setdefault("embed_text", []).append(text)
            if text == "Khái niệm tư tưởng Hồ Chí Minh là gì?":
                return [1.0, 0.0]
            return [0.0, 1.0]

    monkeypatch.setattr(judges, "_get_ragas_llm", lambda: FakeLLM())
    monkeypatch.setattr(judges, "_get_ragas_embeddings", lambda: FakeEmbeddings())

    result = await judges.evaluate_answer_relevance(
        "Khái niệm tư tưởng Hồ Chí Minh là gì?",
        "Tư tưởng Hồ Chí Minh là một hệ thống quan điểm toàn diện và sâu sắc về những vấn đề cơ bản của cách mạng Việt Nam.",
    )

    assert result["score"] == pytest.approx(1.0)
    assert result["reason"] == "Câu trả lời bám sát câu hỏi gốc."
    assert "viết lại bằng tiếng Việt" in calls["prompt"]
    assert "English" not in calls["prompt"]
    assert calls["embed_text"] == [
        "Khái niệm tư tưởng Hồ Chí Minh là gì?",
        "Khái niệm tư tưởng Hồ Chí Minh là gì?",
    ]


@pytest.mark.anyio
async def test_evaluate_faithfulness_uses_vietnamese_judge_prompt(monkeypatch):
    calls: dict[str, object] = {}

    async def fake_score(prompt: str, fallback_reason: str):
        calls["prompt"] = prompt
        calls["fallback_reason"] = fallback_reason
        return {"score": 0.88, "reason": "Câu trả lời bám sát ngữ cảnh."}

    monkeypatch.setattr(judges, "_score_with_vietnamese_judge", fake_score)

    result = await judges.evaluate_faithfulness(
        "Ánh sáng giúp lá cây như thế nào?",
        "Lá cây hấp thụ năng lượng ánh sáng.",
        "Lá cây hấp thụ năng lượng ánh sáng cho quang hợp.",
    )

    assert result == {"score": 0.88, "reason": "Câu trả lời bám sát ngữ cảnh."}
    assert "bộ chấm điểm faithfulness cho hệ thống RAG tiếng Việt" in calls["prompt"]
    assert "Ánh sáng giúp lá cây như thế nào?" in calls["prompt"]
    assert "Lá cây hấp thụ năng lượng ánh sáng." in calls["prompt"]


@pytest.mark.anyio
async def test_evaluate_context_recall_uses_vietnamese_judge_prompt(monkeypatch):
    calls: dict[str, object] = {}

    async def fake_score(prompt: str, fallback_reason: str):
        calls["prompt"] = prompt
        calls["fallback_reason"] = fallback_reason
        return {"score": 0.95, "reason": "Ngữ cảnh đã bao phủ đáp án chuẩn."}

    monkeypatch.setattr(judges, "_score_with_vietnamese_judge", fake_score)

    result = await judges.evaluate_context_recall(
        "Định lý Bayes là gì?",
        "Định lý Bayes cập nhật xác suất bằng chứng dựa trên điều kiện đã biết.",
        ["Định lý Bayes cập nhật xác suất.", "Nó dùng các điều kiện đã biết."],
    )

    assert result == {"score": 0.95, "reason": "Ngữ cảnh đã bao phủ đáp án chuẩn."}
    assert "bộ chấm Context Recall cho RAG tiếng Việt" in calls["prompt"]
    assert "Định lý Bayes là gì?" in calls["prompt"]
    assert "Định lý Bayes cập nhật xác suất bằng chứng dựa trên điều kiện đã biết." in calls["prompt"]
