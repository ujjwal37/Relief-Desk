import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from app.api.auth import get_current_coordinator, CoordinatorUser
from app.models.firestore_models import StoredMatch, StoredRequest, StoredResource, ResourceKind
from app.agents.matching import matching_agent, MatchProposal
from app.tools.storage import storage_service

logger = logging.getLogger("relief_desk.matches_api")
router = APIRouter(prefix="/api", tags=["Matches & Dispatch"])


class ApproveMatchRequest(BaseModel):
    allow_overcommit: bool = False


class RejectMatchRequest(BaseModel):
    reason: str


class ResourceLocationRequest(BaseModel):
    lat: float
    lng: float


@router.get(
    "/requests/{id}/matches",
    response_model=List[MatchProposal],
    summary="Get ranked resource proposals for a request",
)
def get_request_matches(
    id: str,
    top_n: int = Query(default=5, ge=1, le=20),
    user: CoordinatorUser = Depends(get_current_coordinator),
):
    req = storage_service.get_request(id)
    if not req:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Request {id} not found"
        )

    proposals = matching_agent.find_matches(req, top_n=top_n)
    return proposals


@router.post(
    "/matches/{id}/approve",
    response_model=StoredMatch,
    summary="Approve resource dispatch (coordinator action)",
)
def approve_match(
    id: str,
    payload: ApproveMatchRequest = ApproveMatchRequest(),
    user: CoordinatorUser = Depends(get_current_coordinator),
):
    try:
        coordinator_id = user.email
        approved_match = storage_service.approve_match(
            match_id=id,
            approved_by=coordinator_id,
            allow_overcommit=payload.allow_overcommit,
        )
        return approved_match
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))


@router.post(
    "/matches/{id}/reject",
    response_model=StoredMatch,
    summary="Reject resource proposal with reason (coordinator action)",
)
def reject_match(
    id: str,
    payload: RejectMatchRequest,
    user: CoordinatorUser = Depends(get_current_coordinator),
):
    try:
        coordinator_id = user.email
        rejected_match = storage_service.reject_match(
            match_id=id, reason=payload.reason, actor=coordinator_id
        )
        return rejected_match
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))


@router.post(
    "/requests/{id}/arrived",
    response_model=StoredRequest,
    summary="Mark the assigned team as arrived",
)
def mark_request_arrived(
    id: str,
    user: CoordinatorUser = Depends(get_current_coordinator),
):
    try:
        return storage_service.mark_arrived(id, actor=user.email)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))


@router.post(
    "/requests/{id}/complete",
    response_model=StoredRequest,
    summary="Mark the case completed and release team capacity",
)
def complete_request(
    id: str,
    user: CoordinatorUser = Depends(get_current_coordinator),
):
    try:
        return storage_service.complete_request(id, actor=user.email)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))


@router.post(
    "/resources/{id}/location",
    response_model=StoredResource,
    summary="Set a team's last-known location by hand",
)
def update_resource_location(
    id: str,
    payload: ResourceLocationRequest,
    user: CoordinatorUser = Depends(get_current_coordinator),
):
    try:
        return storage_service.update_resource_location(id, payload.lat, payload.lng, actor=user.email)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))


@router.get(
    "/resources",
    response_model=List[StoredResource],
    summary="List available rescue resources and capacity bars",
)
def list_resources(
    kind: Optional[ResourceKind] = None,
    user: CoordinatorUser = Depends(get_current_coordinator),
):
    return storage_service.list_resources(kind=kind)
