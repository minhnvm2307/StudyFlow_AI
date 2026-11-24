"""
LangChain tools for StudyFlow agent (langchain >= 1.0).

Data is pre-fetched asynchronously BEFORE the agent runs, then passed
as closure variables into synchronous tools. This avoids asyncpg
connection-across-thread issues that occur when tools try to open DB
connections from a different event loop / thread.
"""
from typing import Any, Dict, List, Optional
import datetime
import asyncpg
from langchain_core.tools import tool

from app.core.rag.retrieval import retrieve_multi_hop_rag


# ─── Pre-fetcher (called from async context in react_agent.py) ──────────────

async def fetch_agent_context(
    pool: asyncpg.Pool,
    course_id: str,
    user_id: str,
    selected_source_ids: Optional[List[str]] = None,
    selected_topic_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Fetch all DB data needed by the agent tools in one async pass.
    Called from the async run_studyflow_agent before creating the agent.
    """
    from app.services.course_api_service import list_tasks, list_topics, list_chunks

    tasks, all_tasks, topics, chunks = [], [], [], []
    course_name = "Môn học"
    active_topic_titles = []

    # Fetch current course name
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT name FROM subjects WHERE id = $1 AND user_id = $2", course_id, user_id)
            if row:
                course_name = row["name"]
    except Exception as e:
        print(f"[agent ctx] fetch course_name error: {e}")

    # Fetch active topic titles
    if selected_topic_ids:
        try:
            async with pool.acquire() as conn:
                rows = await conn.fetch("SELECT title FROM topics WHERE id = ANY($1::text[])", selected_topic_ids)
                active_topic_titles = [r["title"] for r in rows]
        except Exception as e:
            print(f"[agent ctx] fetch topic titles error: {e}")

    try:
        tasks = await list_tasks(pool, {"courseId": course_id}, user_id) or []
    except Exception as e:
        print(f"[agent ctx] list_tasks error: {e}")

    try:
        all_tasks = await list_tasks(pool, {}, user_id) or []
    except Exception as e:
        print(f"[agent ctx] list_all_tasks error: {e}")

    try:
        topics = await list_topics(pool, course_id, user_id) or []
    except Exception as e:
        print(f"[agent ctx] list_topics error: {e}")

    try:
        chunks = await list_chunks(pool, course_id, user_id) or []
    except Exception as e:
        print(f"[agent ctx] list_chunks error: {e}")

    # Apply filters once at fetch time
    filtered_chunks = chunks
    if selected_source_ids:
        filtered_chunks = [c for c in filtered_chunks if c.get("sourceId") in selected_source_ids]
    if selected_topic_ids:
        filtered_chunks = [
            c for c in filtered_chunks
            if any(tid in selected_topic_ids for tid in (c.get("topicIds") or []))
        ]

    return {
        "pool": pool,
        "course_id": course_id,
        "user_id": user_id,
        "selected_source_ids": selected_source_ids,
        "selected_topic_ids": selected_topic_ids,
        "course_name": course_name,
        "active_topic_titles": active_topic_titles,
        "tasks": tasks,
        "all_tasks": all_tasks,
        "topics": topics,
        "chunks": chunks,           # unfiltered — for topic-specific search
        "filtered_chunks": filtered_chunks,  # filtered — for general search
    }


# ─── Tool factory (called with pre-fetched data — fully sync) ────────────────

def create_agent_tools(ctx: Dict[str, Any]) -> List[Any]:
    """
    Build LangChain tools from pre-fetched context data.
    All tools are synchronous — no DB or async calls inside.
    """
    tasks: List[Dict] = ctx.get("tasks", [])
    all_tasks: List[Dict] = ctx.get("all_tasks", [])
    topics: List[Dict] = ctx.get("topics", [])
    chunks: List[Dict] = ctx.get("chunks", [])
    filtered_chunks: List[Dict] = ctx.get("filtered_chunks", [])

    called_tools = {}

    def is_duplicate(name: str, args: str = "") -> bool:
        key = (name, args)
        if key in called_tools:
            return True
        called_tools[key] = True
        return False

    # ── Tool 1: today's date ────────────────────────────────────────────────
    @tool
    def get_today_date() -> str:
        """
        Trả về ngày hôm nay dưới định dạng YYYY-MM-DD.
        Dùng trước tiên khi người dùng hỏi về lịch học hôm nay, ngày mai
        hoặc bất kỳ ngày cụ thể nào.
        """
        if is_duplicate("get_today_date"):
            return "Bạn đã gọi get_today_date rồi. Không cần gọi lại."
        return datetime.date.today().isoformat()

    # ── Tool 2: study schedule ──────────────────────────────────────────────
    @tool
    def get_study_schedule() -> str:
        """
        Trả về danh sách lịch học chi tiết của các môn học (nhiệm vụ, ngày học,
        trạng thái: todo/done/review). Dùng khi hỏi lịch học.
        """
        if is_duplicate("get_study_schedule"):
            return (
                "Lưu ý: Bạn đã gọi get_study_schedule rồi và kết quả đã được hiển thị ở trên. "
                "Hãy sử dụng kết quả đó để trả lời người dùng ngay, tuyệt đối không được gọi lại công cụ này nữa."
            )
        target_tasks = all_tasks if all_tasks else tasks
        if not target_tasks:
            return "Hiện tại chưa có lịch học nào được xếp."

        today = datetime.date.today().isoformat()
        lines = [f"Lịch học của bạn (hôm nay: {today}):"]
        for idx, t in enumerate(target_tasks, 1):
            date_str = t.get("scheduledDate") or "Chưa xếp ngày"
            subject = t.get("courseName") or t.get("subjectName") or "Môn học"
            title = t.get("title") or t.get("topicTitle") or "Bài học"
            status = t.get("status") or "todo"
            dur = t.get("durationMinutes") or 30
            lines.append(f"{idx}. [{date_str}] Môn {subject}: {title} — {dur} phút — {status}")
        return "\n".join(lines)

    # ── Tool 3: course chapters / topics ────────────────────────────────────
    @tool
    def get_course_chapters() -> str:
        """
        Trả về danh sách tất cả chương và chủ đề của môn học cùng mức độ
        thành thạo (mastery) của người dùng với mỗi chủ đề.
        """
        if is_duplicate("get_course_chapters"):
            return (
                "Lưu ý: Bạn đã gọi get_course_chapters rồi và kết quả đã được hiển thị ở trên. "
                "Hãy sử dụng kết quả đó để trả lời người dùng ngay, tuyệt đối không được gọi lại công cụ này nữa."
            )
        if not topics:
            return "Môn học này chưa được cấu trúc thành các chương/chủ đề."

        lines = ["Danh sách chương và chủ đề:"]
        for idx, t in enumerate(topics, 1):
            title = t.get("title") or "Không tên"
            parent = t.get("parentTopicTitle") or ""
            is_sub = t.get("isSubtopic") or False
            mastery = t.get("masteryPercent") or t.get("mastery") or 0
            if is_sub:
                lines.append(f"   └ {title} (chương: {parent}) — thành thạo {mastery}%")
            else:
                lines.append(f"{idx}. {title} — thành thạo {mastery}%")
        return "\n".join(lines)

    # ── Tool 4: semantic search in course material ──────────────────────────
    @tool
    async def search_course_material(query: str) -> str:
        """
        Tìm kiếm ngữ nghĩa trong tài liệu học tập của môn học.
        Dùng khi người dùng hỏi lý thuyết, khái niệm hoặc bài học cụ thể.
        Tham số query là câu hỏi hoặc từ khóa cần tìm kiếm.
        """
        if is_duplicate("search_course_material", query):
            return (
                f"Lưu ý: Bạn đã tìm kiếm cụm từ '{query}' rồi và kết quả đã được hiển thị ở trên. "
                "Hãy sử dụng kết quả đó để trả lời người dùng ngay, tuyệt đối không được tìm kiếm lại cụm từ này nữa."
            )
        pool = ctx.get("pool")
        course_id = ctx.get("course_id")
        user_id = ctx.get("user_id")
        selected_source_ids = ctx.get("selected_source_ids") or []
        
        if not pool or not course_id or not user_id:
            target = filtered_chunks if filtered_chunks else chunks
            if not target:
                return "Chưa có tài liệu học tập nào được tải lên cho môn học này."
            try:
                ranked, _, _ = retrieve_multi_hop_rag(target, query, [], limit=8, max_hops=3)
            except Exception as e:
                return f"Lỗi tìm kiếm: {e}"
        else:
            try:
                from app.core.rag.retrieval import retrieve_multi_hop_rag_async
                ranked, _, _ = await retrieve_multi_hop_rag_async(
                    pool, course_id, user_id, query, selected_source_ids, limit=8, max_hops=3
                )
            except Exception as e:
                return f"Lỗi tìm kiếm: {e}"

        if not ranked:
            return "Không tìm thấy nội dung liên quan trong tài liệu."

        lines = ["Nội dung trích từ tài liệu học tập:"]
        for idx, c in enumerate(ranked[:5], 1):
            filename = c.get("filename") or "Tài liệu"
            page = c.get("page") or "-"
            sec = c.get("sectionTitle") or ""
            text = (c.get("text") or "")[:700]
            header = f"({filename}, trang {page}{', ' + sec if sec else ''})"
            lines.append(f"\n--- Đoạn {idx} {header} ---\n{text}")
        return "\n".join(lines)

    # ── Tool 5: fetch material by topic id ──────────────────────────────────
    @tool
    def search_by_topic(topic_id: str) -> str:
        """
        Lấy toàn bộ tài liệu liên quan đến một chủ đề cụ thể theo topic_id.
        Dùng khi cần tài liệu chính xác cho một chương đang ôn tập.
        Tham số topic_id là ID của chủ đề, ví dụ: topic-course_xxx-chapter-1.
        """
        if is_duplicate("search_by_topic", topic_id):
            return (
                f"Lưu ý: Bạn đã gọi search_by_topic với topic_id '{topic_id}' rồi và kết quả đã được hiển thị ở trên. "
                "Hãy sử dụng kết quả đó để trả lời người dùng ngay, tuyệt đối không được gọi lại công cụ này nữa."
            )
        matched = [
            c for c in chunks
            if topic_id in (c.get("topicIds") or [])
        ]
        if not matched:
            return f"Không tìm thấy tài liệu nào cho chủ đề {topic_id}."

        lines = [f"Tài liệu cho chủ đề {topic_id}:"]
        for idx, c in enumerate(matched[:8], 1):
            text = (c.get("text") or "")[:600]
            filename = c.get("filename") or "Tài liệu"
            lines.append(f"\n--- Đoạn {idx} ({filename}) ---\n{text}")
        return "\n".join(lines)

    return [
        get_today_date,
        get_study_schedule,
        get_course_chapters,
        search_course_material,
        search_by_topic,
    ]
