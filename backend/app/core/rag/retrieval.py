from __future__ import annotations

import re
from typing import Any

from app.core.rag.text import extract_page_query, normalize_for_search
from app.core.rag.prompts import MULTI_HOP_COORDINATOR_PROMPT


FALLBACK_ANSWER = "The selected documents do not contain enough clear information to answer that. Try selecting another source or asking a more specific question."


def retrieve_chunks(
    chunks: list[dict[str, Any]],
    query: str,
    selected_source_ids: list[str] | None = None,
    limit: int = 8,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """
    Standard retrieval entry point. Performs hybrid search (lexical + vector) if embeddings are available.
    """
    selected = set(selected_source_ids or [])
    scored = hybrid_retrieve(chunks, query, selected, limit=limit)
    scored = [c for c in scored if c.get("score", 0.0) >= 0.35]
    if not scored:
        return [], [], {"mode": "hybrid", "lexicalCount": 0, "vectorCount": 0, "fusedCount": 0}
        
    ranked = [with_citation_passage(chunks, chunk) for chunk in scored]
    refs = dedupe_source_refs([source_ref_from_chunk(chunk) for chunk in ranked])
    debug = {"mode": "hybrid", "lexicalCount": len(scored), "vectorCount": len(scored), "fusedCount": len(scored)}
    return ranked, refs, debug


def hybrid_retrieve(
    chunks: list[dict[str, Any]],
    query: str,
    selected_source_ids: set[str],
    limit: int = 8,
) -> list[dict[str, Any]]:
    """
    Performs in-memory hybrid search (lexical BM25-like + vector cosine similarity).
    """
    filtered = [chunk for chunk in chunks if not selected_source_ids or chunk.get("sourceId") in selected_source_ids or chunk.get("documentId") in selected_source_ids]
    if not filtered:
        return []
        
    normalized_query = normalize_for_search(query)
    terms = [term for term in normalized_query.split() if len(term) >= 2]
    page = extract_page_query(query)
    
    # 1. Lexical score
    lexical_scores = {}
    for chunk in filtered:
        lexical_scores[chunk["id"]] = score_chunk(chunk, terms, normalized_query, page)
        
    max_lex = max(lexical_scores.values(), default=1.0)
    if max_lex == 0:
        max_lex = 1.0
    for cid in lexical_scores:
        lexical_scores[cid] /= max_lex
        
    # 2. Vector similarity score
    from app.core.rag.embedding import get_embedding, cosine_similarity
    query_vector = get_embedding(query)
    vector_scores = {}
    
    for chunk in filtered:
        chunk_vector = chunk.get("embedding")
        if chunk_vector:
            sim = cosine_similarity(query_vector, chunk_vector)
            vector_scores[chunk["id"]] = (sim + 1.0) / 2.0
        else:
            vector_scores[chunk["id"]] = 0.0
            
    # 3. Combine scores
    scored = []
    for chunk in filtered:
        cid = chunk["id"]
        # Weighting: 40% lexical, 60% vector
        final_score = 0.4 * lexical_scores.get(cid, 0.0) + 0.6 * vector_scores.get(cid, 0.0)
        
        # Exact matching phrase boost
        if normalized_query and normalized_query in (chunk.get("normalizedText") or ""):
            final_score += 0.3
            
        # Page match boost
        chunk_page = chunk.get("pageStart") or chunk.get("page")
        if page and chunk_page == page:
            final_score += 5.0
            
        if final_score > 0.0:
            scored.append({**chunk, "score": final_score})
            
    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:limit]


def retrieve_multi_hop_rag(
    chunks: list[dict[str, Any]],
    query: str,
    selected_source_ids: list[str] | None = None,
    limit: int = 8,
    max_hops: int = 5,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """
    Decomposes the query and retrieves chunks across multiple hops (up to max_hops).
    """
    from app.core.document.llm_section_split import complete_text
    
    selected = set(selected_source_ids or [])
    current_query = query
    accumulated_chunks = {}
    hops_taken = []
    
    for hop in range(1, max_hops + 1):
        hop_results = hybrid_retrieve(chunks, current_query, selected, limit=4)
        hop_results = [c for c in hop_results if c.get("score", 0.0) >= 0.35]
        if not hop_results:
            hops_taken.append({"hop": hop, "query": current_query, "status": "no_results"})
            break
            
        new_added = 0
        for chunk in hop_results:
            cid = chunk["id"]
            if cid not in accumulated_chunks:
                accumulated_chunks[cid] = chunk
                new_added += 1
                
        hops_taken.append({
            "hop": hop,
            "query": current_query,
            "results_count": len(hop_results),
            "new_chunks_added": new_added
        })
        
        if hop == max_hops:
            break
            
        # Construct summary of what we know so far
        currently_retrieved_text = ""
        for idx, chunk in enumerate(accumulated_chunks.values(), start=1):
            currently_retrieved_text += f"[{idx}] {chunk.get('filename')}: {chunk.get('text')[:250]}...\n\n"
            
        system_content = MULTI_HOP_COORDINATOR_PROMPT
        user_content = (
            f"Original User Query: {query}\n\n"
            f"Currently Retrieved Excerpts:\n{currently_retrieved_text}\n"
            f"Decide if we need another hop. Output '[DONE]' or the next single search query:"
        )
        
        try:
            decision = complete_text([
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content}
            ], temperature=0.1, max_tokens=100).strip()
        except Exception:
            decision = "[DONE]"
            
        if decision.upper() == "[DONE]" or not decision:
            break
            
        current_query = decision
        
    final_scored = list(accumulated_chunks.values())
    final_scored.sort(key=lambda item: item.get("score", 0.0), reverse=True)
    
    ranked = [with_citation_passage(chunks, chunk) for chunk in final_scored[:limit]]
    refs = dedupe_source_refs([source_ref_from_chunk(chunk) for chunk in ranked])
    
    debug = {
        "mode": "multi_hop_hybrid",
        "hops_taken": hops_taken,
        "total_accumulated": len(accumulated_chunks),
    }
    return ranked, refs, debug


async def retrieve_multi_hop_rag_generator(
    chunks: list[dict[str, Any]],
    query: str,
    selected_source_ids: list[str] | None = None,
    limit: int = 8,
    max_hops: int = 5,
):
    import asyncio
    from app.core.document.llm_section_split import complete_text
    
    selected = set(selected_source_ids or [])
    current_query = query
    accumulated_chunks = {}
    hops_taken = []
    
    for hop in range(1, max_hops + 1):
        yield {"type": "hop", "hop": hop, "query": current_query, "status": "searching"}
        
        hop_results = hybrid_retrieve(chunks, current_query, selected, limit=4)
        hop_results = [c for c in hop_results if c.get("score", 0.0) >= 0.35]
        if not hop_results:
            hops_taken.append({"hop": hop, "query": current_query, "status": "no_results"})
            yield {"type": "hop", "hop": hop, "query": current_query, "status": "done", "results_count": 0, "new_chunks_added": 0}
            break
            
        new_added = 0
        for chunk in hop_results:
            cid = chunk["id"]
            if cid not in accumulated_chunks:
                accumulated_chunks[cid] = chunk
                new_added += 1
                
        hops_taken.append({
            "hop": hop,
            "query": current_query,
            "results_count": len(hop_results),
            "new_chunks_added": new_added
        })
        
        yield {"type": "hop", "hop": hop, "query": current_query, "status": "done", "results_count": len(hop_results), "new_chunks_added": new_added}
        
        if hop == max_hops:
            break
            
        # Construct summary of what we know so far
        currently_retrieved_text = ""
        for idx, chunk in enumerate(accumulated_chunks.values(), start=1):
            currently_retrieved_text += f"[{idx}] {chunk.get('filename')}: {chunk.get('text')[:250]}...\n\n"
            
        system_content = MULTI_HOP_COORDINATOR_PROMPT
        user_content = (
            f"Original User Query: {query}\n\n"
            f"Currently Retrieved Excerpts:\n{currently_retrieved_text}\n"
            f"Decide if we need another hop. Output '[DONE]' or the next single search query:"
        )
        
        try:
            decision = await asyncio.to_thread(
                complete_text,
                [
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": user_content}
                ],
                0.1,
                100
            )
            decision = decision.strip()
        except Exception:
            decision = "[DONE]"
            
        if decision.upper() == "[DONE]" or not decision:
            break
            
        current_query = decision
        
    final_scored = list(accumulated_chunks.values())
    final_scored.sort(key=lambda item: item.get("score", 0.0), reverse=True)
    
    ranked = [with_citation_passage(chunks, chunk) for chunk in final_scored[:limit]]
    refs = dedupe_source_refs([source_ref_from_chunk(chunk) for chunk in ranked])
    
    debug = {
        "mode": "multi_hop_hybrid",
        "hops_taken": hops_taken,
        "total_accumulated": len(accumulated_chunks),
    }
    
    yield {"type": "retrieval_done", "ranked": ranked, "refs": refs, "debug": debug}


def score_chunk(chunk: dict[str, Any], terms: list[str], normalized_query: str, page: int | None) -> float:
    haystack = chunk.get("normalizedText") or normalize_for_search(" ".join([
        str(chunk.get("sectionPath") or ""),
        str(chunk.get("sectionTitle") or ""),
        str(chunk.get("text") or ""),
    ]))
    score = 1.0 if not terms else 0.0
    chunk_page = chunk.get("pageStart") or chunk.get("page")
    if page and chunk_page == page:
        score += 500.0
    if normalized_query and normalized_query in haystack:
        score += max(10.0, len(terms) * len(terms) * 4.0)
    for term in terms:
        if term in haystack:
            score += 3.0 if len(term) > 3 else 1.0
    return score


def source_ref_from_chunk(chunk: dict[str, Any], index: int = 0) -> dict[str, Any]:
    passage = chunk.get("citationText") or chunk.get("text") or chunk.get("quote") or ""
    source_id = chunk.get("sourceId") or chunk.get("documentId")
    page = chunk.get("pageStart") or chunk.get("page")
    section = chunk.get("citationSection") or chunk.get("sectionPath") or " > ".join(
        value for value in [chunk.get("chapterName"), chunk.get("topicName")] if value
    )
    return {
        "id": index + 1,
        "sourceId": source_id,
        "documentId": chunk.get("documentId") or source_id,
        "chunkId": chunk.get("chunkId") or chunk.get("id"),
        "chunkIds": chunk.get("citationChunkIds") or [chunk.get("chunkId") or chunk.get("id")],
        "filename": chunk.get("filename"),
        "page": page,
        "pageStart": page,
        "pageEnd": chunk.get("pageEnd") or page,
        "section": section,
        "sectionTitle": chunk.get("sectionTitle") or chunk.get("topicName"),
        "quote": passage,
        "passage": passage,
        "excerpt": re.sub(r"\s+", " ", passage)[:240],
    }


def dedupe_source_refs(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for ref in refs:
        key = f"{ref.get('documentId')}:{ref.get('section')}:{ref.get('passage')}"
        if key in seen:
            continue
        seen.add(key)
        out.append({**ref, "id": len(out) + 1})
        if len(out) >= 8:
            break
    return out


def with_citation_passage(all_chunks: list[dict[str, Any]], chunk: dict[str, Any]) -> dict[str, Any]:
    source_id = chunk.get("sourceId") or chunk.get("documentId")
    ordered = sorted(
        [item for item in all_chunks if source_id in {item.get("sourceId"), item.get("documentId")}],
        key=lambda item: int(item.get("chunkIndex") or 0),
    )
    chunk_id = chunk.get("chunkId") or chunk.get("id")
    index = next((i for i, item in enumerate(ordered) if (item.get("chunkId") or item.get("id")) == chunk_id), -1)
    if index < 0:
        return {**chunk, "citationText": chunk.get("text", ""), "citationChunkIds": [chunk_id]}

    citation_chunks = [ordered[index]]
    previous_chunk = ordered[index - 1] if index > 0 else None
    next_chunk = ordered[index + 1] if index + 1 < len(ordered) else None
    if same_page(chunk, next_chunk):
        citation_chunks = [ordered[index], next_chunk]
    elif same_page(chunk, previous_chunk):
        citation_chunks = [previous_chunk, ordered[index]]

    first = ordered.index(citation_chunks[0]) + 1
    last = ordered.index(citation_chunks[-1]) + 1
    return {
        **chunk,
        "citationText": "\n\n".join(str(item.get("text") or "").strip() for item in citation_chunks).strip()[:1900],
        "citationChunkIds": [item.get("chunkId") or item.get("id") for item in citation_chunks],
        "citationSection": f"Chunk {first}" if first == last else f"Chunks {first}-{last}",
    }


def same_page(a: dict[str, Any] | None, b: dict[str, Any] | None) -> bool:
    if not a or not b:
        return False
    ap = a.get("pageStart") or a.get("page")
    bp = a.get("pageStart") or b.get("page")
    if ap is None and bp is None:
        return True
    return ap == bp


async def retrieve_candidates_from_db(
    pool,
    course_id: str,
    user_id: str,
    query: str,
    selected_source_ids: list[str] | None = None,
    limit: int = 50
) -> list[dict[str, Any]]:
    from app.core.rag.embedding import get_embedding
    query_vector = get_embedding(query)
    query_vector_str = f"[{','.join(str(x) for x in query_vector)}]"
    
    params = [course_id, user_id]
    where_clauses = ["subject_id = $1", "user_id = $2"]
    if selected_source_ids:
        params.append(selected_source_ids)
        where_clauses.append(f"source_id = ANY(${len(params)})")
        
    vector_params = list(params)
    vector_params.append(query_vector_str)
    vector_params.append(limit)
    vector_query = f"""
        SELECT id, subject_id, text, page, page_start, page_end, section_path, section_title, topic_ids, filename, source_id, chunk_index, (embedding::real[]) as embedding, metadata
        FROM document_chunks
        WHERE {" AND ".join(where_clauses)}
        ORDER BY embedding <=> ${len(vector_params) - 1}::vector
        LIMIT ${len(vector_params)}
    """
    
    lexical_clauses = list(where_clauses)
    lexical_params = list(params)
    words = [w.strip() for w in query.split() if len(w.strip()) >= 2]
    for w in words[:5]:
        lexical_params.append(f"%{w}%")
        lexical_clauses.append(f"text ILIKE ${len(lexical_params)}")
        
    lexical_params.append(limit)
    lexical_query = f"""
        SELECT id, subject_id, text, page, page_start, page_end, section_path, section_title, topic_ids, filename, source_id, chunk_index, (embedding::real[]) as embedding, metadata
        FROM document_chunks
        WHERE {" AND ".join(lexical_clauses)}
        LIMIT ${len(lexical_params)}
    """
    
    async with pool.acquire() as conn:
        vector_rows = await conn.fetch(vector_query, *vector_params)
        if words:
            lexical_rows = await conn.fetch(lexical_query, *lexical_params)
        else:
            lexical_rows = []
            
    seen = set()
    candidates = []
    
    def add_row(row):
        row_dict = dict(row)
        row_dict["topicIds"] = row_dict.pop("topic_ids", None) or []
        row_dict["sourceId"] = row_dict.pop("source_id", None)
        row_dict["chunkIndex"] = row_dict.pop("chunk_index", None)
        row_dict["pageStart"] = row_dict.pop("page_start", None)
        row_dict["pageEnd"] = row_dict.pop("page_end", None)
        row_dict["sectionPath"] = row_dict.pop("section_path", None)
        row_dict["sectionTitle"] = row_dict.pop("section_title", None)
        
        cid = row_dict["id"]
        if cid not in seen:
            seen.add(cid)
            candidates.append(row_dict)
            
    for r in vector_rows:
        add_row(r)
    for r in lexical_rows:
        add_row(r)
        
    return candidates

async def retrieve_multi_hop_rag_async(
    pool,
    course_id: str,
    user_id: str,
    query: str,
    selected_source_ids: list[str] | None = None,
    limit: int = 8,
    max_hops: int = 5,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    from app.core.document.llm_section_split import complete_text
    
    current_query = query
    accumulated_chunks = {}
    hops_taken = []
    
    for hop in range(1, max_hops + 1):
        candidates = await retrieve_candidates_from_db(pool, course_id, user_id, current_query, selected_source_ids, limit=50)
        hop_results = hybrid_retrieve(candidates, current_query, set(), limit=4)
        hop_results = [c for c in hop_results if c.get("score", 0.0) >= 0.35]
        if not hop_results:
            hops_taken.append({"hop": hop, "query": current_query, "status": "no_results"})
            break
            
        new_added = 0
        for chunk in hop_results:
            cid = chunk["id"]
            if cid not in accumulated_chunks:
                chunk_with_cit = with_citation_passage(candidates, chunk)
                accumulated_chunks[cid] = chunk_with_cit
                new_added += 1
                
        hops_taken.append({
            "hop": hop,
            "query": current_query,
            "results_count": len(hop_results),
            "new_chunks_added": new_added
        })
        
        if hop == max_hops:
            break
            
        currently_retrieved_text = ""
        for idx, chunk in enumerate(accumulated_chunks.values(), start=1):
            currently_retrieved_text += f"[{idx}] {chunk.get('filename')}: {chunk.get('text')[:250]}...\n\n"
            
        system_content = MULTI_HOP_COORDINATOR_PROMPT
        user_content = (
            f"Original User Query: {query}\n\n"
            f"Currently Retrieved Excerpts:\n{currently_retrieved_text}\n"
            f"Decide if we need another hop. Output '[DONE]' or the next single search query:"
        )
        
        try:
            import asyncio
            decision = await asyncio.to_thread(
                complete_text,
                [
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": user_content}
                ],
                0.1,
                100
            )
            decision = decision.strip()
        except Exception:
            decision = "[DONE]"
            
        if decision.upper() == "[DONE]" or not decision:
            break
            
        current_query = decision
        
    final_scored = list(accumulated_chunks.values())
    final_scored.sort(key=lambda item: item.get("score", 0.0), reverse=True)
    
    ranked = final_scored[:limit]
    refs = dedupe_source_refs([source_ref_from_chunk(chunk) for chunk in ranked])
    
    debug = {
        "mode": "multi_hop_hybrid",
        "hops_taken": hops_taken,
        "total_accumulated": len(accumulated_chunks),
    }
    return ranked, refs, debug

