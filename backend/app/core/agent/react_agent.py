"""
StudyFlow ReAct agent — compatible with langchain >= 1.0.

Flow:
  1. Pre-fetch all DB data (tasks, topics, chunks) in async context
  2. Build sync tools from pre-fetched data (no asyncpg cross-thread issues)
  3. Create agent with create_agent() and invoke via ainvoke()
"""
from typing import Dict, List, Optional
import asyncpg
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage

from app.config import settings
from app.core.agent.tools import fetch_agent_context, create_agent_tools


SYSTEM_PROMPT = """Bạn là Trợ lý AI học tập của StudyFlow. Trả lời ngắn gọn, đúng trọng tâm và LUÔN bằng Tiếng Việt.
Quy trình công cụ:
- Lịch học: Đầu tiên gọi get_today_date, sau đó ở lượt phản hồi tiếp theo mới gọi get_study_schedule. Không bao giờ gọi cả hai công cụ cùng lúc.
- Lý thuyết/Khái niệm: Gọi search_course_material.
- Tài liệu theo chương: Gọi search_by_topic với topic_id tương ứng.
- Danh sách chương: Gọi get_course_chapters.
Nguyên tắc:
1. Chỉ được gọi tối đa MỘT công cụ trong mỗi lượt phản hồi. Tuyệt đối không gọi nhiều công cụ cùng lúc.
2. Không bịa thông tin. Trả lời sư phạm, lịch sự.
3. Nếu người dùng hỏi ngoài phạm vi học tập hoặc các câu hỏi không liên quan đến môn học, lịch học, tài liệu môn học (ví dụ: công thức nấu ăn như pizza, làm bánh, giải trí, v.v.), bạn phải lịch sự xin lỗi và từ chối trả lời, đồng thời khuyên họ quay lại chủ đề học tập của môn học."""


def _build_messages(history: List[Dict[str, str]], message: str):
    msgs = []
    for h in (history or []):
        role, content = h.get("role", ""), h.get("content", "")
        if role == "user":
            msgs.append(HumanMessage(content=content))
        elif role == "assistant":
            msgs.append(AIMessage(content=content))
    msgs.append(HumanMessage(content=message))
    return msgs


async def run_studyflow_agent(
    pool: asyncpg.Pool,
    course_id: str,
    user_id: str,
    message: str,
    history_messages: List[Dict[str, str]],
    selected_source_ids: Optional[List[str]] = None,
    selected_topic_ids: Optional[List[str]] = None,
) -> str:
    """
    Run the LangChain v1.x agent for a user chat message.

    All DB fetching happens here (async), then sync tools get the data
    via closure — no asyncpg cross-thread issues.
    """
    # 1. Pre-fetch all data we need (async, same event loop as FastAPI)
    ctx = await fetch_agent_context(
        pool, course_id, user_id, selected_source_ids, selected_topic_ids
    )

    # 2. Build sync tools from pre-fetched data
    tools = create_agent_tools(ctx)

    # 3. Configure LLM
    api_key = settings.CUSTOM_API_KEY or settings.OPENAI_API_KEY or "no-key"
    base_url = settings.CUSTOM_URL if (settings.CUSTOM_URL and settings.CUSTOM_URL.strip()) else None
    llm = ChatOpenAI(
        model=settings.LLM_MODEL or "gpt-4o-mini",
        api_key=api_key,
        base_url=base_url,
        temperature=0.3,
    )
    # Force parallel_tool_calls=False to avoid Nvidia NIM / Llama-3.1 template issues
    original_bind_tools = llm.bind_tools
    def bound_tools_override(tools, **kwargs):
        kwargs["parallel_tool_calls"] = False
        return original_bind_tools(tools, **kwargs)
    object.__setattr__(llm, 'bind_tools', bound_tools_override)

    # Build dynamic prompt with course and topic context
    course_name = ctx.get("course_name", "Môn học")
    active_topic_titles = ctx.get("active_topic_titles", [])
    if active_topic_titles:
        topic_context_str = f"\n- Chủ đề/chương đang học/ôn tập hiện tại: {', '.join(active_topic_titles)}"
    else:
        topic_context_str = "\n- Chưa có chủ đề cụ thể nào được chọn làm tiêu điểm học tập lúc này."

    dynamic_prompt = f"""{SYSTEM_PROMPT}

Bối cảnh môn học/người dùng hiện tại:
- Môn học hiện tại: {course_name}{topic_context_str}
"""

    # 4. Create agent (returns LangGraph CompiledStateGraph)
    agent = create_agent(
        model=llm,
        tools=tools,
        system_prompt=dynamic_prompt,
    )

    # 5. Invoke
    input_messages = _build_messages(history_messages, message)
    try:
        result = await agent.ainvoke(
            {"messages": input_messages},
            config={"recursion_limit": 15}
        )
        for msg in reversed(result.get("messages", [])):
            if isinstance(msg, AIMessage) and msg.content:
                return msg.content
        return "Xin lỗi, tôi không thể xử lý yêu cầu lúc này."
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[StudyFlow Agent] error: {e}")
        return await _fallback_llm(message, history_messages)


async def _fallback_llm(message: str, history: List[Dict[str, str]]) -> str:
    """Direct OpenAI call when the agent fails."""
    try:
        from app.core.document.llm_section_split import get_openai_client
        client = get_openai_client()
        msgs = [{"role": "system", "content": "Bạn là trợ lý học tập. Hãy trả lời bằng tiếng Việt."}]
        for h in (history or []):
            msgs.append({"role": h.get("role", "user"), "content": h.get("content", "")})
        msgs.append({"role": "user", "content": message})
        completion = client.chat.completions.create(
            model=settings.LLM_MODEL or "gpt-4o-mini",
            messages=msgs,
            temperature=0.5,
        )
        return completion.choices[0].message.content or ""
    except Exception as err:
        return f"Rất tiếc, đã xảy ra lỗi hệ thống: {err}"
