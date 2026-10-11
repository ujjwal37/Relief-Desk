from fastapi import APIRouter, Depends, HTTPException, status
from app.tools.scoring import scoring_engine, UrgencyWeights
from app.tools.storage import storage_service
from app.api.auth import get_current_coordinator, CoordinatorUser
from app.config import settings

router = APIRouter(prefix="/api/config", tags=["Configuration"])


@router.get("/weights", response_model=UrgencyWeights)
def get_urgency_weights(
    coordinator: CoordinatorUser = Depends(get_current_coordinator),
):
    return scoring_engine.weights


@router.put("/weights", response_model=UrgencyWeights)
def update_urgency_weights(
    payload: UrgencyWeights,
    coordinator: CoordinatorUser = Depends(get_current_coordinator),
):
    before = scoring_engine.weights.model_dump()
    updated = scoring_engine.update_weights(payload)
    storage_service.record_audit(
        actor=coordinator.email,
        action="weights_updated",
        target="config/weights",
        before=before,
        after=updated.model_dump(),
    )
    return updated


_PLACEHOLDER_MAP_KEYS = {"", "replace-me", "your-key", "changeme"}


@router.get("/maps")
def maps_browser_config():
    """Browser Maps key. Placeholder values stay off so the SVG map is used."""
    key = (settings.GOOGLE_MAPS_API_KEY or "").strip()
    if key.lower() in _PLACEHOLDER_MAP_KEYS:
        return {"enabled": False, "apiKey": None}
    return {"enabled": True, "apiKey": key}
