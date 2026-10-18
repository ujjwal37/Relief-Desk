"""Text embeddings for duplicate retrieval.

gemini-embedding-001, task SEMANTIC_SIMILARITY, 768 dimensions.
https://ai.google.dev/gemini-api/docs/embeddings
Vectors shorter than 3072 are normalized here, which that page requires for this model.
When the key is missing, callers use the lexical fallback instead of a fake vector.
"""
import logging
import math
import time
from typing import Any, List, Optional

from app.config import settings
from app.llm.client import llm_client

logger = logging.getLogger("relief_desk.llm")

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
        from app.llm.client import (
            build_genai_client,
            _is_vertex_fallback_error,
            _log_vertex_warning,
            _short_fallback_reason,
        )
    except ImportError:
        return None
    try:
        from google.genai import types
    except ImportError:
        types = None
    call_start = time.perf_counter()
    provider = "vertex" if settings.is_vertex_backend else "gemini"
    model_name = settings.GEMINI_EMBED_MODEL
    fallback_reason = "none"
    call_ok = False
    last_err: Optional[BaseException] = None
    client = None
    result = None
    try:
        try:
            timeout_s = float(settings.EMBED_TIMEOUT_S or 3.0)
            client, provider = build_genai_client(timeout_s=timeout_s)
            embed_cfg: Any = {
                "task_type": settings.GEMINI_EMBED_TASK,
                "output_dimensionality": settings.GEMINI_EMBED_DIM,
            }
            if types is not None and hasattr(types, "EmbedContentConfig"):
                try:
                    embed_cfg = types.EmbedContentConfig(**embed_cfg)
                except Exception:
                    pass
            try:
                result = client.models.embed_content(
                    model=model_name,
                    contents=list(texts),
                    config=embed_cfg,
                )
                call_ok = True
            except Exception as exc:
                if provider == "vertex" and _is_vertex_fallback_error(exc) and llm_client.studio_key_live():
                    _log_vertex_warning(f"Vertex embedding call failed ({exc}); falling back to AI Studio.")
                    fallback_reason = _short_fallback_reason(exc)
                    studio_client, studio_provider = build_genai_client(timeout_s=timeout_s, force_studio=True)
                    try:
                        result = studio_client.models.embed_content(
                            model=model_name,
                            contents=list(texts),
                            config=embed_cfg,
                        )
                        call_ok = True
                        close = getattr(client, "close", None)
                        if close:
                            try:
                                close()
                            except Exception:
                                pass
                        client = studio_client
                        provider = studio_provider
                    except Exception as studio_exc:
                        call_ok = False
                        last_err = studio_exc
                        close = getattr(studio_client, "close", None)
                        if close:
                            try:
                                close()
                            except Exception:
                                pass
                        raise
                else:
                    call_ok = False
                    last_err = exc
                    raise
            finally:
                close = getattr(client, "close", None)
                if close:
                    try:
                        close()
                    except Exception:
                        pass
        except Exception as exc:
            if not last_err:
                last_err = exc
            return None
    finally:
        latency_ms = int((time.perf_counter() - call_start) * 1000)
        ok_str = "true" if call_ok else "false"
        if not call_ok and fallback_reason == "none":
            fallback_reason = _short_fallback_reason(last_err)
        log_provider = "aistudio" if provider == "gemini" else provider
        logger.info(
            "gemini_call provider=%s model=%s latency_ms=%d ok=%s fallback_reason=%s",
            log_provider,
            model_name,
            latency_ms,
            ok_str,
            fallback_reason,
        )
    vectors: List[List[float]] = []
    for embedding in getattr(result, "embeddings", None) or []:
        values = list(getattr(embedding, "values", None) or [])
        if len(values) != settings.GEMINI_EMBED_DIM:
            return None
        vectors.append(l2_normalize(values))
    if len(vectors) != len(texts):
        return None
    return vectors
