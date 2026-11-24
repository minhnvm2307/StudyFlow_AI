import ast
import json
import os
import re
from openai import OpenAI
from fastapi import HTTPException
from app.schemas import Topic
from app.core.scheduler.bkt import BKTModel
from app.config import settings

def load_env():
    if os.path.exists(".env"):
        with open(".env") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip()
                    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                        v = v[1:-1]
                    os.environ[k] = v

load_env()

def get_openai_client() -> OpenAI:
    api_key = settings.CUSTOM_API_KEY or settings.OPENAI_API_KEY
    base_url = settings.CUSTOM_URL
    if not api_key:
        raise HTTPException(status_code=400, detail="LLM API credentials not configured.")
    base_url = base_url if (base_url and base_url.strip()) else None
    default_headers = {}
    if settings.LLM_PROVIDER == "openrouter":
        if settings.OPENROUTER_REFERER:
            default_headers["HTTP-Referer"] = settings.OPENROUTER_REFERER
        if settings.OPENROUTER_APP_TITLE:
            default_headers["X-Title"] = settings.OPENROUTER_APP_TITLE
    return OpenAI(
        api_key=api_key,
        base_url=base_url,
        default_headers=default_headers or None,
        timeout=max(1.0, settings.LLM_TIMEOUT_MS / 1000),
        max_retries=2,
    )

def parse_json_from_llm(content: str) -> dict | list:
    content = content.strip()
    if "<think>" in content and "</think>" in content:
        content = content.split("</think>", 1)[1].strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content, flags=re.IGNORECASE).strip()
        content = re.sub(r"\s*```$", "", content).strip()
        
    first_brace = content.find("{")
    first_bracket = content.find("[")
    
    start_idx = -1
    end_idx = -1
    
    if first_brace != -1 and (first_bracket == -1 or first_brace < first_bracket):
        start_idx = first_brace
        end_idx = content.rfind("}")
    elif first_bracket != -1:
        start_idx = first_bracket
        end_idx = content.rfind("]")
        
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        content = content[start_idx:end_idx + 1].strip()
        
    parsers = [json.loads, ast.literal_eval]
    for parser in parsers:
        try:
            return parser(content)
        except Exception:
            pass

    repaired = re.sub(r"([\{,]\s*)([A-Za-z_][A-Za-z0-9_-]*)\s*:", r'\1"\2":', content)
    repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
    for parser in parsers:
        try:
            return parser(repaired)
        except Exception:
            pass

    return json.loads(content)

def complete_json(system_content: str, user_content: str, temperature: float, max_tokens: int | None = None) -> dict | list:
    client = get_openai_client()
    base_kwargs = {
        "model": settings.LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ],
        "temperature": temperature,
    }
    if max_tokens is not None:
        base_kwargs["max_tokens"] = max_tokens
    elif settings.LLM_MAX_TOKENS:
        base_kwargs["max_tokens"] = settings.LLM_MAX_TOKENS
    if settings.LLM_TOP_P is not None:
        base_kwargs["top_p"] = settings.LLM_TOP_P
    use_response_format_order = [False, True] if settings.LLM_PROVIDER == "openrouter" else [True, False]
    last_error: Exception | None = None
    last_raw = ""
    for use_response_format in use_response_format_order:
        kwargs = dict(base_kwargs)
        if use_response_format:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            response = client.chat.completions.create(**kwargs)
            last_raw = response.choices[0].message.content or ""
            return parse_json_from_llm(last_raw)
        except Exception as exc:
            last_error = exc
    raise ValueError(f"Could not parse JSON from LLM response: {last_error}; raw={last_raw[:160]!r}")

def complete_text(messages: list[dict[str, str]], temperature: float = 0.2, max_tokens: int | None = None) -> str:
    client = get_openai_client()
    kwargs = {
        "model": settings.LLM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens if max_tokens is not None else (settings.LLM_MAX_TOKENS or 900),
    }
    if settings.LLM_TOP_P is not None:
        kwargs["top_p"] = settings.LLM_TOP_P
    response = client.chat.completions.create(**kwargs)
    return (response.choices[0].message.content or "").strip()

def split_text_into_sections(text: str, target_size: int = 3500) -> list[str]:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return [text] if text.strip() else []
    
    sections = []
    current_section = []
    current_len = 0
    
    for p in paragraphs:
        if len(p) > target_size:
            # If paragraph is too big, split it by sentence ends
            sentence_ends = re.compile(r"(?<=[.!?])\s+")
            sentences = [s.strip() for s in sentence_ends.split(p) if s.strip()]
            for s in sentences:
                if current_len + len(s) + 1 > target_size and current_len > 0:
                    sections.append(" ".join(current_section))
                    current_section = [s]
                    current_len = len(s)
                else:
                    current_section.append(s)
                    current_len += len(s) + 1
        else:
            if current_len + len(p) + 2 > target_size and current_len > 0:
                sections.append("\n\n".join(current_section))
                current_section = [p]
                current_len = len(p)
            else:
                current_section.append(p)
                current_len += len(p) + 2
                
    if current_section:
        if all("\n" not in item for item in current_section):
            sections.append(" ".join(current_section))
        else:
            sections.append("\n\n".join(current_section))
    return sections


def split_document_to_sections_via_llm(document_text: str, subject_id: str) -> list[Topic]:
    from app.core.rag.pipeline import parse_pages, build_sections
    
    pages = parse_pages(document_text)
    sections = build_sections(subject_id, pages)
    
    topics = []
    section_number = 1
    
    for sec in sections:
        sec_text = sec.text.strip()
        if not sec_text:
            continue
            
        if len(sec_text) > 4500:
            parts = split_text_into_sections(sec_text, target_size=3500)
            for idx, part in enumerate(parts, start=1):
                part = part.strip()
                if not part:
                    continue
                title = sec.section_title
                if len(parts) > 1:
                    title = f"{title} (Phần {idx})"
                
                description = part.replace("\n", " ")[:200].strip()
                if len(part) > 200:
                    description += "..."
                
                topics.append(Topic(
                    id=f"topic-{subject_id}-{section_number}",
                    subject_id=subject_id,
                    title=title,
                    section_number=section_number,
                    description=description,
                    content_chunk=part[:3000],
                    mastery=0.05,
                    p_l0=0.05,
                    p_t=BKTModel.NORMAL_PRIORS["p_t"],
                    p_g=BKTModel.NORMAL_PRIORS["p_g"],
                    p_s=BKTModel.NORMAL_PRIORS["p_s"],
                    awaiting_diagnostic=True,
                ))
                section_number += 1
        else:
            description = sec_text.replace("\n", " ")[:200].strip()
            if len(sec_text) > 200:
                description += "..."
            topics.append(Topic(
                id=f"topic-{subject_id}-{section_number}",
                subject_id=subject_id,
                title=sec.section_title,
                section_number=section_number,
                description=description,
                content_chunk=sec_text[:3000],
                mastery=0.05,
                p_l0=0.05,
                p_t=BKTModel.NORMAL_PRIORS["p_t"],
                p_g=BKTModel.NORMAL_PRIORS["p_g"],
                p_s=BKTModel.NORMAL_PRIORS["p_s"],
                awaiting_diagnostic=True,
            ))
            section_number += 1
            
    if not topics and document_text.strip():
        description = document_text.replace("\n", " ")[:200].strip()
        if len(document_text) > 200:
            description += "..."
        topics.append(Topic(
            id=f"topic-{subject_id}-1",
            subject_id=subject_id,
            title="General Concept",
            section_number=1,
            description=description,
            content_chunk=document_text[:3000],
            mastery=0.05,
            p_l0=0.05,
            p_t=BKTModel.NORMAL_PRIORS["p_t"],
            p_g=BKTModel.NORMAL_PRIORS["p_g"],
            p_s=BKTModel.NORMAL_PRIORS["p_s"],
            awaiting_diagnostic=True,
        ))
        
    return topics

def llm_generate_quiz(section_title: str, content_chunk: str) -> list[dict]:
    prompt = f"""
Generate a multiple-choice quiz of 3 questions based on the following study content.
Each question must have exactly 4 choices (A, B, C, D) and exactly 1 correct answer.

Return a JSON object containing a "questions" key with an array of questions. Follow this JSON format strictly:
{{
  "questions": [
    {{
      "question": "The question content?",
      "choices": {{
        "A": "Choice A",
        "B": "Choice B",
        "C": "Choice C",
        "D": "Choice D"
      }},
      "correct_answer": "A"
    }}
  ]
}}

Content:
---
{content_chunk}
---
"""
    try:
        data = complete_json(
            "You are a quiz generator. Respond only with structured JSON and no markdown fences.",
            prompt,
            0.3,
        )
        questions = data.get("questions", [])
        if not questions:
            raise HTTPException(status_code=500, detail="LLM returned empty questions list.")
        return questions
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(status_code=500, detail=f"LLM Quiz Generation Error: {str(e)}")
