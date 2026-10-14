"""Text embeddings for duplicate retrieval.

gemini-embedding-001, task SEMANTIC_SIMILARITY, 768 dimensions.
https://ai.google.dev/gemini-api/docs/embeddings
Vectors shorter than 3072 are normalized here, which that page requires for this model.
When the key is missing, callers use the lexical fallback instead of a fake vector.
"""
import math
from typing import List, Optional

from app.config import settings
from app.llm.client import llm_client

DIM = 768


def l2_normalize(values: List[float]) -> List[float]:
    norm = math.sqrt(sum(item * item for item in values))
    if norm == 0:
        return list(values)
    return [item / norm for item in values]


def cosine(left: List[float], right: List[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def describe() -> str:
    """The embedder named in duplicate evidence. A test provider is never called Gemini."""
    from app.llm import openai_compat as oc

    if oc.requested():
        return f"{oc.embed_model() or 'no embedding model'} via {oc.label()} cosine"
    return f"{settings.GEMINI_EMBED_MODEL} {settings.GEMINI_EMBED_TASK} {settings.GEMINI_EMBED_DIM}d cosine"


def embed_texts(texts: List[str]) -> Optional[List[List[float]]]:
    """768-d unit vectors, or None when Gemini cannot be called.

    Antigravity mode does not call the Gemini embedding API. openai_compat uses
    OPENAI_COMPAT_EMBED_MODEL when it is set. Otherwise callers use the lexical
    duplicate check instead.
    """
    from app.llm import openai_compat as oc
    from app.llm.antigravity import antigravity_requested

    if oc.requested():
        if not texts or not oc.enabled() or not oc.embed_model():
            return None
        try:
            vectors = oc.embed(list(texts))
        except Exception:
            return None
        return [l2_normalize(v) for v in vectors] if vectors else None
    if antigravity_requested() or not texts or not llm_client.gemini_live():
        return None
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return None
    try:
        client = genai.Client(
            api_key=settings.GEMINI_API_KEY,
            http_options={
                "timeout": int(float(settings.EMBED_TIMEOUT_S or 3.0) * 1000),
                "retry_options": {"attempts": 1},
            },
        )
        result = client.models.embed_content(
            model=settings.GEMINI_EMBED_MODEL,
            contents=list(texts),
            config=types.EmbedContentConfig(
                task_type=settings.GEMINI_EMBED_TASK,
                output_dimensionality=settings.GEMINI_EMBED_DIM,
            ),
        )
    except Exception:
        return None
    vectors: List[List[float]] = []
    for embedding in getattr(result, "embeddings", None) or []:
        values = list(getattr(embedding, "values", None) or [])
        if len(values) != settings.GEMINI_EMBED_DIM:
            return None
        vectors.append(l2_normalize(values))
    if len(vectors) != len(texts):
        return None
    return vectors
