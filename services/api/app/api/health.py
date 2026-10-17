from fastapi import APIRouter
from app.config import settings
from app.llm.client import llm_client

router = APIRouter(tags=["Health"])

@router.get("/healthz")
@router.get("/api/health")
def health_check():
    """Health check endpoint: does not call Gemini or external services."""
    return {
        "status": "ok",
        "app": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "gemini_enabled": settings.GEMINI_ENABLED,
        "demo_mode": settings.DEMO_MODE
    }


@router.get("/api/health/ai")
def ai_health():
    """Provider, cache hit rate, and quota. Does not include the API key."""
    from app.llm import openai_compat as oc

    looked = llm_client.cache_hits + llm_client.cache_misses
    rate = (llm_client.cache_hits / looked) if looked else 0.0
    from app.llm import antigravity as ag

    import os
    from urllib.parse import urlparse
    base = os.environ.get("GOOGLE_GEMINI_BASE_URL") or os.environ.get("GEMINI_BASE_URL") or ""
    try:
        # Where the SDK will really send calls (env or SDK config). A localhost base is the local test AI, not Gemini.
        import google.genai as _genai  # type: ignore
        base = base or str(_genai.Client(api_key="unused")._api_client._http_options.base_url or "")
    except Exception:
        pass
    local_base = (urlparse(base).hostname or "") in ("127.0.0.1", "localhost", "0.0.0.0")
    if ag.antigravity_enabled() or local_base:
        # Local test mode (off by default, never production): calls go to the local CLI, not Gemini.
        provider, model, label = "antigravity-local", "local", "Local test AI"
    elif oc.enabled():
        provider, model, label = oc.PROVIDER, oc.model(), oc.label()
    elif (
        llm_client.gemini_live()
        and bool(llm_client.guard.last_success_at)
        and not (llm_client.guard.circuit_open() or llm_client.guard.failing())
    ):
        provider, model, label = "gemini", settings.GEMINI_MODEL, "Gemini live"
    else:
        provider, model, label = "fallback", settings.GEMINI_MODEL, "Gemini unavailable, built-in rules used"
    return {
        "provider": provider,
        "model": model,
        "label": label,
        "embed_model": (oc.embed_model() or None) if oc.requested() else settings.GEMINI_EMBED_MODEL,
        "cache_hit_rate": round(rate, 3),
        "last_success_at": llm_client.guard.last_success_iso,
        "quota": {
            "daily_cap": llm_client.daily_cap,
            "calls": llm_client.call_count,
            "circuit": "open" if llm_client.guard.circuit_open() else "closed",
            "last_success": bool(llm_client.guard.last_success_at),
            "last_failure": llm_client.guard.last_failure_reason or None if llm_client.guard.failing() else None,
        },
    }
