from __future__ import annotations

import asyncio
import math
import sys
import types
from functools import lru_cache
from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from app.config import settings
from app.core.rag.embedding import get_embedding, get_embeddings


def _ensure_ragas_import_compat() -> None:
    if "langchain_community.chat_models.vertexai" in sys.modules:
        return

    vertexai_module = types.ModuleType("langchain_community.chat_models.vertexai")
    vertexai_module.ChatVertexAI = type("ChatVertexAI", (), {})
    sys.modules[vertexai_module.__name__] = vertexai_module


_ensure_ragas_import_compat()

from ragas.embeddings.base import BaseRagasEmbedding
from ragas.llms import llm_factory


class _StudyFlowEmbeddings(BaseRagasEmbedding):
    def embed_text(self, text: str, **kwargs: Any) -> list[float]:
        return get_embedding(text)

    async def aembed_text(self, text: str, **kwargs: Any) -> list[float]:
        return await asyncio.to_thread(get_embedding, text)

    def embed_texts(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        return get_embeddings(texts)

    async def aembed_texts(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        return await asyncio.to_thread(get_embeddings, texts)


class VietnameseScoreOutput(BaseModel):
    diem: float = Field(ge=0.0, le=1.0)
    ly_do: str = ""


class VietnameseQuestionOutput(BaseModel):
    cau_hoi_suy_ra: str
    khong_cam_ket: bool = False
    ly_do: str = ""


def _get_eval_api_key() -> str:
    api_key = (settings.CUSTOM_API_KEY or settings.OPENAI_API_KEY or "").strip()
    if not api_key:
        raise RuntimeError("Missing eval LLM API key for ragas judges.")
    return api_key


def _get_eval_base_url() -> str | None:
    base_url = (settings.CUSTOM_URL or settings.OPENAI_BASE_URL or "").strip()
    return base_url or None


def _get_eval_model() -> str:
    return settings.LLM_MODEL or settings.OPENAI_MODEL or "gpt-4o-mini"


@lru_cache(maxsize=1)
def _get_ragas_llm():
    client = AsyncOpenAI(
        api_key=_get_eval_api_key(),
        base_url=_get_eval_base_url(),
    )
    return llm_factory(
        _get_eval_model(),
        provider="openai",
        client=client,
        temperature=0.0,
    )


@lru_cache(maxsize=1)
def _get_ragas_embeddings() -> BaseRagasEmbedding:
    return _StudyFlowEmbeddings()


def _coerce_contexts(context: str | list[str]) -> list[str]:
    if isinstance(context, list):
        return [item for item in context if item and item.strip()]
    if context and context.strip():
        return [context]
    return []


def _score_payload(score: float, reason: str) -> dict[str, float | str]:
    bounded = max(0.0, min(1.0, float(score)))
    return {"score": bounded, "reason": reason.strip()}


async def _score_with_vietnamese_judge(prompt: str, fallback_reason: str) -> dict[str, float | str]:
    result = await _get_ragas_llm().agenerate(prompt, VietnameseScoreOutput)
    score = getattr(result, "diem", 0.0)
    reason = getattr(result, "ly_do", "") or fallback_reason
    return _score_payload(score, reason)


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def evaluate_faithfulness(
    user_input: str,
    context: str | list[str],
    answer: str,
) -> dict[str, float | str]:
    contexts = _coerce_contexts(context)
    if not contexts:
        return _score_payload(0.0, "Không có ngữ cảnh truy xuất để kiểm tra độ bám sát câu trả lời.")

    prompt = f"""
Bạn là bộ chấm điểm faithfulness cho hệ thống RAG tiếng Việt.
Chỉ trả lời theo schema của model đầu ra.

Yêu cầu:
- Cho điểm `diem` từ 0.0 đến 1.0.
- `diem` cao khi câu trả lời chỉ dùng thông tin có trong ngữ cảnh.
- `diem` thấp khi câu trả lời lạc đề, né tránh, hoặc thêm thông tin không được hỗ trợ.
- `ly_do` phải ngắn gọn, bằng tiếng Việt.

Câu hỏi người dùng:
{user_input}

Ngữ cảnh truy xuất:
{chr(10).join(contexts)}

Câu trả lời cần chấm:
{answer}
""".strip()
    return await _score_with_vietnamese_judge(
        prompt,
        "Điểm faithfulness được chấm từ mức độ bám sát ngữ cảnh truy xuất.",
    )


async def evaluate_answer_relevance(query: str, answer: str) -> dict[str, float | str]:
    lowered_answer = answer.lower()
    if "xin lỗi" in lowered_answer and "tư tưởng hồ chí minh" not in lowered_answer:
        return _score_payload(0.0, "Câu trả lời né tránh câu hỏi thay vì trả lời trực tiếp.")

    prompt = f"""
Bạn là bộ chấm Answer Relevance cho RAG tiếng Việt.
Nhiệm vụ của bạn là đọc câu trả lời rồi viết lại bằng tiếng Việt một câu hỏi ngắn mà câu trả lời đó đang trực tiếp giải đáp.

Yêu cầu:
- `cau_hoi_suy_ra`: chỉ viết một câu hỏi tiếng Việt ngắn.
- `khong_cam_ket`: đặt là true nếu câu trả lời né tránh, quá chung chung, hoặc không trả lời câu hỏi nào rõ ràng.
- `ly_do`: giải thích ngắn gọn bằng tiếng Việt.

Câu trả lời:
{answer}
""".strip()

    generated = await _get_ragas_llm().agenerate(prompt, VietnameseQuestionOutput)
    reverse_question = getattr(generated, "cau_hoi_suy_ra", "").strip()
    if not reverse_question or getattr(generated, "khong_cam_ket", False):
        return _score_payload(0.0, getattr(generated, "ly_do", "") or "Câu trả lời không trực tiếp giải đáp câu hỏi.")

    embeddings = _get_ragas_embeddings()
    query_vec = await embeddings.aembed_text(query)
    reverse_vec = await embeddings.aembed_text(reverse_question)
    score = _cosine_similarity(query_vec, reverse_vec)
    reason = getattr(generated, "ly_do", "") or "Độ liên quan được tính bằng mức giống nhau giữa câu hỏi gốc và câu hỏi suy ra từ câu trả lời."
    return _score_payload(score, reason)


async def evaluate_context_recall(
    query: str,
    ground_truth: str,
    context: str | list[str],
) -> dict[str, float | str]:
    contexts = _coerce_contexts(context)
    if not contexts:
        return _score_payload(0.0, "Không có ngữ cảnh truy xuất để đánh giá recall.")

    prompt = f"""
Bạn là bộ chấm Context Recall cho RAG tiếng Việt.
Chỉ trả lời theo schema của model đầu ra.

Yêu cầu:
- Cho điểm `diem` từ 0.0 đến 1.0.
- `diem` cao khi ngữ cảnh truy xuất đã chứa đủ dữ kiện để tái tạo đáp án chuẩn.
- `diem` thấp khi thiếu ý quan trọng trong đáp án chuẩn.
- `ly_do` phải ngắn gọn, bằng tiếng Việt.

Câu hỏi người dùng:
{query}

Đáp án chuẩn:
{ground_truth}

Ngữ cảnh truy xuất:
{chr(10).join(contexts)}
""".strip()
    return await _score_with_vietnamese_judge(
        prompt,
        "Điểm context recall phản ánh mức độ đầy đủ của ngữ cảnh so với đáp án chuẩn.",
    )
