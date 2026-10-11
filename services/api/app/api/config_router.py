from fastapi import APIRouter, HTTPException, status
from app.tools.scoring import scoring_engine, UrgencyWeights
from app.tools.storage import storage_service

router = APIRouter(prefix="/api/config", tags=["Configuration"])


@router.get("/weights", response_model=UrgencyWeights)
def get_urgency_weights():
    return scoring_engine.weights


@router.put("/weights", response_model=UrgencyWeights)
def update_urgency_weights(payload: UrgencyWeights):
    before = scoring_engine.weights.model_dump()
    updated = scoring_engine.update_weights(payload)
    storage_service.record_audit(
        actor="coordinator",
        action="weights_updated",
        target="config/weights",
        before=before,
        after=updated.model_dump(),
    )
    return updated
