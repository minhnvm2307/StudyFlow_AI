from app.schemas import Topic, StudyTask
from app.config import MERGE_JACCARD_THRESHOLD, MAX_SECTIONS_PER_SUBJECT

def jaccard_similarity(text_a: str, text_b: str) -> float:
    a, b = set(text_a.lower().split()), set(text_b.lower().split())
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)

def find_merge_candidate(new_chunk: str, existing_topics: list[Topic]) -> Topic | None:
    best, best_score = None, 0.0
    for t in existing_topics:
        score = jaccard_similarity(new_chunk, t.content_chunk)
        if score > MERGE_JACCARD_THRESHOLD and score > best_score:
            best, best_score = t, score
    return best

def merge_topic_content(target: Topic, source_chunk: str, source_id: str) -> Topic:
    target.content_chunk = f"{target.content_chunk}\n\n{source_chunk}".strip()
    if source_id not in target.merged_from:
        target.merged_from.append(source_id)
    return target

def cap_max_sections(topics: list[Topic], tasks: list[StudyTask]) -> tuple[list[Topic], list[StudyTask]]:
    while len(topics) > MAX_SECTIONS_PER_SUBJECT:
        best_pair, best_score = None, -1.0
        for i in range(len(topics)):
            for j in range(i + 1, len(topics)):
                score = jaccard_similarity(topics[i].content_chunk, topics[j].content_chunk)
                if score > best_score:
                    best_pair, best_score = (i, j), score
        i, j = best_pair
        keep, drop = topics[i], topics[j]
        keep = merge_topic_content(keep, drop.content_chunk, drop.id)
        topics[i] = keep
        for t in tasks:
            if t.topic_id == drop.id:
                t.topic_id = keep.id
        topics.pop(j)
    return topics, tasks
