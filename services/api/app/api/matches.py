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
    confirm_take: bool = False  # kept for older clients; the warning is shown before Approve
    check_take: bool = False  # opt-in: refuse with 409 when a more urgent case loses its best team


def _would_take_from(match: StoredMatch) -> Optional[dict]:
    """A more urgent waiting case whose best team is this one. None when nobody loses out."""
    req = storage_service.get_request(match.request_id)
    if req is None:
        return None
    from app.models.firestore_models import RequestStatus
    from app.api.public import public_code_for
    waiting = {RequestStatus.NEW, RequestStatus.NEEDS_RECHECK, RequestStatus.MATCHED}
    for other in sorted(storage_service.list_requests(), key=lambda r: -(r.urgency_score or 0)):
        if other.id == req.id or other.merged_into or other.status not in waiting:
            continue
        if (other.urgency_score or 0) <= (req.urgency_score or 0):
            break
        if other.hoax_reason or {"hoax", "likely_hoax"} & set(other.flags or []):
            continue
        try:
            props = matching_agent.find_matches(other, top_n=2, save_to_storage=False)
        except Exception:
            continue
        if not props or props[0].resource_id != match.resource_id:
            continue
        nxt = props[1] if len(props) > 1 else None
        return {
            "case_id": other.id,
            "case_ref": other.public_code or public_code_for(other.report_ids[0] if other.report_ids else other.id),
            "case_urgency": round(other.urgency_score or 0),
            "team": props[0].resource_name,
            "next_team": nxt.resource_name if nxt else None,
            "next_km": nxt.breakdown.distance_km if nxt else None,
        }
    return None


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
    # Warn, never block: mark a team that a more urgent waiting case would also get first.
    for prop in proposals:
        stored = storage_service._matches.get(prop.match_id)
        if stored is not None:
            try:
                prop.takes_from = _would_take_from(stored)
            except Exception:  # pragma: no cover - a warning must never break the list
                prop.takes_from = None
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
    match = storage_service._matches.get(id)
    if match is not None:
        from app.tools.case_queue import approve_blocked
        case = storage_service.get_request(match.request_id)
        if case is not None and approve_blocked(case):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "ai_not_finished"})
    if match is not None and payload.check_take and not payload.confirm_take and match.state.value == "proposed":
        taken = _would_take_from(match)
        if taken:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "takes_best_team", **taken})
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


@router.post("/matches/{id}/undo", response_model=StoredMatch, summary="Undo a just-approved dispatch")
def undo_match(id: str, user: CoordinatorUser = Depends(get_current_coordinator)):
    try:
        return storage_service.undo_approval(match_id=id, actor=user.email)
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


@router.get("/requests/{id}/no-team", summary="Why no team fits, and the options left")
def no_team(id: str, user: CoordinatorUser = Depends(get_current_coordinator)):
    from app.agents.no_team import no_team_options
    req = storage_service.get_request(id)
    if req is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return no_team_options(req, storage_service.list_resources(event_id=req.event_id))


class NoTeamChoice(BaseModel):
    option: str


@router.post("/requests/{id}/no-team", summary="Log the coordinator's choice when no team fits")
def choose_no_team(id: str, payload: NoTeamChoice, user: CoordinatorUser = Depends(get_current_coordinator)):
    from app.agents.no_team import OPTIONS, no_team_options
    if payload.option not in OPTIONS:
        raise HTTPException(status_code=400, detail="Unknown option")
    req = storage_service.get_request(id)
    if req is None:
        raise HTTPException(status_code=404, detail="Case not found")
    opts = no_team_options(req, storage_service.list_resources(event_id=req.event_id))
    chosen = opts["options"].get(payload.option)
    if payload.option != "escalate" and not chosen:
        raise HTTPException(status_code=400, detail="That option is not available for this case")
    before = req.model_dump()
    req.flags = sorted(set((req.flags or []) + [f"no_team_{payload.option}"]))
    storage_service._requests[req.id] = req
    storage_service.record_audit(actor=user.email, action=f"no_team_{payload.option}", target=req.id, before=before, after=req.model_dump())
    return {"request_id": req.id, "option": payload.option, "chosen": chosen, "sent": False}


class DismissHoaxRequest(BaseModel):
    reason: Optional[str] = None


@router.post(
    "/requests/{id}/dismiss-hoax",
    response_model=StoredRequest,
    summary="Close a report the coordinator confirmed is a hoax",
)
def dismiss_hoax(
    id: str,
    payload: DismissHoaxRequest = DismissHoaxRequest(),
    user: CoordinatorUser = Depends(get_current_coordinator),
):
    try:
        return storage_service.dismiss_hoax(id, actor=user.email, reason=payload.reason)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))


@router.post(
    "/requests/{id}/send-nearest-boat",
    response_model=StoredMatch,
    summary="One tap from a life-threat card: send the nearest free boat",
)
def send_nearest_boat(
    id: str,
    user: CoordinatorUser = Depends(get_current_coordinator),
):
    """A person presses this. Matching stays deterministic. The AI may still be checking."""
    from app.tools.case_queue import is_life_threat
    req = storage_service.get_request(id)
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    if not is_life_threat(req):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": "not_life_threat"})
    if req.status in ("dispatched", "approved", "in_progress", "completed"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Already sent")
    # A life-threat send is a boat even when the report was read as medical.
    from app.models.schemas import IncidentType
    as_rescue = req if req.type == IncidentType.RESCUE else req.model_copy(update={"type": IncidentType.RESCUE})
    proposals = matching_agent.find_matches(as_rescue, top_n=5, save_to_storage=True)
    boats = [p for p in proposals if getattr(p.resource_kind, "value", p.resource_kind) == "boat"]
    if not boats:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "no_boat"})
    nearest = min(boats, key=lambda p: (p.breakdown.distance_km if p.breakdown else 1e9, p.resource_id))
    try:
        return storage_service.approve_match(nearest.match_id, approved_by=user.email)
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


class TeamActionRequest(BaseModel):
    action: str


@router.get(
    "/team/{resource_id}",
    response_model=StoredResource,
    summary="One team, for the field confirm link",
)
def get_team(resource_id: str):
    res = storage_service.get_resource(resource_id)
    if not res:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    return res


@router.post(
    "/team/{resource_id}",
    response_model=StoredResource,
    summary="At scene, done, or back available",
)
def confirm_team(resource_id: str, payload: TeamActionRequest):
    try:
        return storage_service.team_action(resource_id, payload.action, actor="team")
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))


@router.post(
    "/team/{resource_id}/location",
    response_model=StoredResource,
    summary="Optional location share from the team phone",
)
def share_team_location(resource_id: str, payload: ResourceLocationRequest):
    try:
        return storage_service.update_resource_location(resource_id, payload.lat, payload.lng, actor="team")
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
