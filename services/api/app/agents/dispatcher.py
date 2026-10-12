"""Assist-mode dispatcher. Tools propose a hold. Commit does not run until a person confirms."""
import uuid
from typing import List

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

from app.config import settings
from app.models.firestore_models import MatchBreakdown, MatchState, RequestStatus, StoredMatch
from app.tools.storage import storage_service

_calls: List[str] = []


def calls() -> List[str]:
    return list(_calls)


def reset_calls() -> None:
    _calls.clear()


def list_open_cases() -> list:
    """Open cases that are not dispatched."""
    _calls.append("list_open_cases")
    closed = {RequestStatus.DISPATCHED, RequestStatus.COMPLETED, RequestStatus.RESOLVED, RequestStatus.CLOSED}
    rows = []
    for req in storage_service.list_requests():
        if req.merged_into or req.status in closed:
            continue
        rows.append({
            "id": req.id,
            "type": req.type.value,
            "people": req.people_count or 1,
            "place": req.place_text,
            "status": req.status.value,
        })
    return rows


def find_teams(kind: str, lat: float | None = None, lng: float | None = None) -> list:
    """Free or finishing-soon teams of this kind with a fresh position, closest live ETA first."""
    from app.tools.geo import haversine_distance
    from app.tracking.availability import candidate_kind, cite_sentence
    from app.tracking.live import live_eta

    _calls.append("find_teams")
    found = []
    for res in storage_service.list_resources():
        if res.kind.value != kind:
            continue
        if res.hold_request_id or res.capacity_remaining <= 0:
            continue
        availability = candidate_kind(res)
        if availability is None:
            continue
        distance = 0.0
        eta = None
        if lat is not None and lng is not None:
            distance = round(haversine_distance(res.lat, res.lng, lat, lng), 1)
            eta, far = live_eta(distance, res.kind.value)
            if far:
                continue
        rank = (eta if eta is not None else 10_000) + (8 if availability == "soon_free" else 0)
        found.append({
            "id": res.id,
            "name": res.name,
            "free": res.capacity_remaining,
            "availability": availability,
            "finishing_soon": availability == "soon_free",
            "simulated": bool(res.simulated) or res.location_source == "simulated",
            "distance_km": distance,
            "eta_minutes": eta,
            "rank": rank,
            "note": cite_sentence(res, distance),
        })
    found.sort(key=lambda row: (row["rank"], -row["free"], row["id"]))
    return found


def check_capacity(resource_id: str) -> dict:
    """Seats left on one team. Does not change them."""
    _calls.append("check_capacity")
    res = storage_service.get_resource(resource_id)
    if res is None:
        return {"resource_id": resource_id, "free": 0}
    return {"resource_id": resource_id, "free": res.capacity_remaining, "held": bool(res.hold_request_id)}


def propose_assignment(request_id: str, resource_id: str) -> dict:
    """Save a proposal and hold the seats. The case stays undispatched."""
    _calls.append("propose_assignment")
    req = storage_service.get_request(request_id)
    res = storage_service.get_resource(resource_id)
    if req is None or res is None:
        return {"ok": False, "explanation": "That case or team is not on the board."}
    from app.tools.geo import haversine_distance
    from app.tracking.availability import cite_sentence, proposal_block_reason

    if proposal_block_reason(res):
        return {
            "ok": False,
            "dispatched": False,
            "explanation": "That team is busy, off duty, or its position is stale.",
        }
    distance = 0.0
    if req.lat is not None and req.lng is not None:
        distance = round(haversine_distance(res.lat, res.lng, req.lat, req.lng), 1)
    note = cite_sentence(res, distance)
    people = req.people_count or 1
    try:
        hold = storage_service.reserve_hold(request_id, resource_id, people, actor="dispatcher")
    except ValueError as exc:
        return {
            "ok": False,
            "dispatched": False,
            "explanation": f"Not enough teams for the demand. {exc}",
        }
    match = StoredMatch(
        id=f"match_{uuid.uuid4().hex[:10]}",
        request_id=request_id,
        resource_id=resource_id,
        score=1.0,
        breakdown=MatchBreakdown(
            distance_km=0.0,
            distance_score=0.0,
            capacity_fit_score=0.0,
            urgency_score=0.0,
            vulnerability_fit_score=0.0,
            total_score=1.0,
        ),
        explanation=note,
        state=MatchState.PROPOSED,
    )
    storage_service.save_match(match, actor="dispatcher")
    req.status = RequestStatus.NEW
    return {"ok": True, "match_id": match.id, "dispatched": False, "hold": hold}


def reserve_hold(request_id: str, resource_id: str, people: int) -> dict:
    """Transactional claim used by the proposal step."""
    _calls.append("reserve_hold")
    try:
        return storage_service.reserve_hold(request_id, resource_id, people, actor="dispatcher")
    except ValueError as exc:
        return {"held": False, "dispatched": False, "explanation": str(exc)}


def commit_dispatch(request_id: str, resource_id: str, confirmed: bool = False) -> dict:
    """Dispatch only after a person confirms. The ADK tool requires that confirmation."""
    _calls.append("commit_dispatch")
    if not confirmed:
        return {"dispatched": False, "needs_confirmation": True, "request_id": request_id}
    match = next(
        (
            item for item in storage_service.list_matches_for_request(request_id)
            if item.resource_id == resource_id and item.state == MatchState.PROPOSED
        ),
        None,
    )
    if match is None:
        return {"dispatched": False, "explanation": "No proposal is waiting for approval."}
    approved = storage_service.approve_match(match.id, approved_by="coordinator")
    return {"dispatched": approved.state.value == "approved", "match_id": match.id}


def build_dispatcher() -> LlmAgent:
    commit = FunctionTool(commit_dispatch, require_confirmation=True)
    return LlmAgent(
        name="DispatcherAssist",
        model=settings.GEMINI_MODEL,
        description="Proposes a team. A person approves before anyone is dispatched.",
        instruction=(
            "Call the tools in order: list_open_cases, find_teams, check_capacity, "
            "propose_assignment, reserve_hold. Explain a shortage when teams are fewer than the demand. "
            "Do not call commit_dispatch until a coordinator confirms."
        ),
        tools=[
            FunctionTool(list_open_cases),
            FunctionTool(find_teams),
            FunctionTool(check_capacity),
            FunctionTool(propose_assignment),
            FunctionTool(reserve_hold),
            commit,
        ],
        output_key="dispatch_proposal",
    )


DISPATCHER = build_dispatcher()
