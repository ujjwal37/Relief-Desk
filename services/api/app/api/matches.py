"""Coordinator match approval. A human must approve every dispatch."""

import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.models.firestore_models import StoredMatch, StoredResource
from app.tools.capacity import (
    CALL_112,
    CapacityDecision,
    CapacityError,
    MatchIneligible,
    MatchNotFound,
    MatchStateError,
    OvercommitRequired,
    RequestNotFound,
    ResourceNotFound,
    ResourceUnavailable,
    capacity_service,
)

logger = logging.getLogger("relief_desk.matches")

router = APIRouter(prefix="/api", tags=["Matches & Resources"])


class ProposeMatchPayload(BaseModel):
    request_id: str = Field(..., min_length=1)
    resource_id: str = Field(..., min_length=1)
    actor: str = Field(default="coordinator", min_length=1, max_length=80)


class ApproveMatchPayload(BaseModel):
    approved_by: str = Field(default="coordinator", min_length=1, max_length=80)
    override: bool = False


class RejectMatchPayload(BaseModel):
    rejected_by: str = Field(default="coordinator", min_length=1, max_length=80)
    reason: str = Field(..., min_length=3, max_length=500)


def _http_error(exc: CapacityError) -> HTTPException:
    if isinstance(exc, OvercommitRequired):
        logger.info("Overcommit blocked: %s", exc.decision.warning)
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=exc.decision.model_dump(mode="json"),
        )
    if isinstance(exc, (MatchNotFound, RequestNotFound, ResourceNotFound)):
        logger.warning("Match lookup failed: %s", exc)
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, MatchIneligible):
        logger.info("Match ineligible: %s", exc)
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, (MatchStateError, ResourceUnavailable)):
        logger.info("Match state rejected the action: %s", exc)
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    logger.warning("Capacity error: %s", exc)
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/resources", response_model=list[StoredResource])
def list_resources():
    try:
        return capacity_service.list_resources()
    except Exception as exc:
        logger.exception("Failed to list resources")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from exc


@router.get("/resources/{resource_id}", response_model=StoredResource)
def get_resource(resource_id: str):
    try:
        return capacity_service.get_resource(resource_id)
    except CapacityError as exc:
        raise _http_error(exc) from exc
    except Exception as exc:
        logger.exception("Failed to read resource %s", resource_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from exc


@router.post("/matches", response_model=StoredMatch, status_code=status.HTTP_201_CREATED)
def propose_match(payload: ProposeMatchPayload):
    try:
        return capacity_service.propose_match(
            request_id=payload.request_id,
            resource_id=payload.resource_id,
            actor=payload.actor,
        )
    except CapacityError as exc:
        raise _http_error(exc) from exc
    except Exception as exc:
        logger.exception("Failed to propose match")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from exc


@router.get("/matches/{match_id}", response_model=StoredMatch)
def get_match(match_id: str):
    try:
        return capacity_service.get_match(match_id)
    except CapacityError as exc:
        raise _http_error(exc) from exc
    except Exception as exc:
        logger.exception("Failed to read match %s", match_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from exc


@router.post("/matches/{match_id}/approve", response_model=CapacityDecision)
def approve_match(match_id: str, payload: ApproveMatchPayload):
    """Human approval. Decrements capacity. Overcommit requires override."""
    try:
        decision = capacity_service.approve_match(
            match_id,
            approved_by=payload.approved_by,
            override=payload.override,
        )
        if decision.call_112 != CALL_112:
            decision.call_112 = CALL_112
        return decision
    except CapacityError as exc:
        raise _http_error(exc) from exc
    except Exception as exc:
        logger.exception("Failed to approve match %s", match_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from exc


@router.post("/matches/{match_id}/reject", response_model=CapacityDecision)
def reject_match(match_id: str, payload: RejectMatchPayload):
    try:
        return capacity_service.reject_match(
            match_id,
            rejected_by=payload.rejected_by,
            reason=payload.reason,
        )
    except CapacityError as exc:
        raise _http_error(exc) from exc
    except Exception as exc:
        logger.exception("Failed to reject match %s", match_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from exc
