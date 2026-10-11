from fastapi import APIRouter
from app.config import settings

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
