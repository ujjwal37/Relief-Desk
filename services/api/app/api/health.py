from fastapi import APIRouter
from app.config import settings
from app.llm.client import llm_client

router = APIRouter(tags=["Health"])

@router.get("/healthz")
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
    if oc.enabled():
        provider, model, label = oc.PROVIDER, oc.model(), oc.label()
    elif llm_client.gemini_live():
        provider, model, label = "gemini", settings.GEMINI_MODEL, "Gemini"
    else:
        provider, model, label = "fallback", settings.GEMINI_MODEL, "Rules"
    return {
        "provider": provider,
        "model": model,
        "label": label,
        "embed_model": (oc.embed_model() or None) if oc.requested() else settings.GEMINI_EMBED_MODEL,
        "cache_hit_rate": round(rate, 3),
        "quota": {
            "daily_cap": llm_client.daily_cap,
            "calls": llm_client.call_count,
            "circuit": "open" if llm_client.guard.circuit_open() else "closed",
        },
    }
