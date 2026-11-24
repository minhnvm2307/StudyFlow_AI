import os
import math
from openai import OpenAI
from app.config import settings

def get_fpt_client() -> OpenAI:
    api_key = os.getenv("FPT_API_KEY")
    base_url = os.getenv("FPT_URL")
    return OpenAI(api_key=api_key, base_url=base_url)

def get_embedding(text: str) -> list[float]:
    """
    Generate vector embedding using FPT OpenAI-compatible API client.
    Falls back to a pseudo-semantic hash vector of 1024 dimensions if the API is offline or fails.
    """
    if not text.strip():
        return [0.0] * 1024
        
    try:
        client = get_fpt_client()
        model = os.getenv("EMBEDDING_MODEL", "Vietnamese_Embedding")
        response = client.embeddings.create(input=[text], model=model)
        emb = response.data[0].embedding
        
        # Ensure we always return exactly 1024 dimensions
        if len(emb) < 1024:
            return emb + [0.0] * (1024 - len(emb))
        return emb[:1024]
    except Exception as e:
        # Fallback to pseudo-embedding of 1024 dimensions
        return _generate_pseudo_embedding(text)

def get_embeddings(texts: list[str]) -> list[list[float]]:
    """
    Generate vector embeddings in batch using FPT OpenAI-compatible API client.
    Falls back to pseudo-embeddings if the API fails.
    """
    if not texts:
        return []
        
    cleaned_texts = [t.strip() for t in texts]
    if not any(cleaned_texts):
        return [[0.0] * 1024 for _ in texts]
        
    try:
        client = get_fpt_client()
        model = os.getenv("EMBEDDING_MODEL", "Vietnamese_Embedding")
        
        # Batch requests to FPT API
        response = client.embeddings.create(input=cleaned_texts, model=model)
        embs = [d.embedding for d in response.data]
        
        # Ensure dimensions
        result = []
        for emb in embs:
            if len(emb) < 1024:
                emb = emb + [0.0] * (1024 - len(emb))
            result.append(emb[:1024])
        return result
    except Exception as e:
        # Fallback to individual pseudo-embeddings
        return [_generate_pseudo_embedding(t) for t in texts]

def _generate_pseudo_embedding(text: str) -> list[float]:
    import hashlib
    vec = [0.0] * 1024
    normalized = text.lower().strip()
    words = [w for w in normalized.split() if len(w) > 2]
    
    if not words:
        words = ["empty"]
        
    for i, word in enumerate(words):
        h = int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16)
        idx = h % 1024
        vec[idx] += 1.0 / (math.log(i + 2) + 1.0)
        
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec

def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
