"""Assist proposals. Planning holds a team. Nothing here sets a case to dispatched."""
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Set

from fastapi import APIRouter, Depends

from app.agents.dispatcher import find_teams, propose_assignment
from app.api.auth import DEMO_COORDINATOR_EMAIL, CoordinatorUser, get_current_coordinator
from app.models.firestore_models import MatchState, RequestStatus
from app.tools.storage import storage_service

router = APIRouter(prefix="/api/assist", tags=["Assist"])

HOLD = timedelta(minutes=10)
_LAST_SHORTAGES: Dict[str, List[dict]] = {}
SOUTH = {f"ward_{i}" for i in range(1, 7)}
NORTH = {f"ward_{i}" for i in range(7, 13)}
ALL_WARDS = SOUTH | NORTH
CLOSED = {
    RequestStatus.DISPATCHED,
    RequestStatus.COMPLETED,
    RequestStatus.RESOLVED,
    RequestStatus.CLOSED,
    RequestStatus.APPROVED,
    RequestStatus.IN_PROGRESS,
}


def is_demo_coordinator(email: str) -> bool:
    return (email or "").lower() == DEMO_COORDINATOR_EMAIL


def wards_for(email: str) -> Set[str]:
    """South sees Alappuzha and Ernakulam. North sees Thrissur and Wayanad.

    The demo coordinator runs the whole synthetic flood, so a report from Ward 7
    is not hidden from them. Other accounts stay on the south desk.
    """
    mail = (email or "").lower()
    if mail.startswith("north-"):
        return set(NORTH)
    if mail.startswith("south-"):
        return set(SOUTH)
    if is_demo_coordinator(mail):
        return set(ALL_WARDS)
    return set(SOUTH)


def visible_to(email: str, ward_id: str | None) -> bool:
    """Unknown ward stays visible for the demo coordinator. A scoped desk does not guess."""
    if is_demo_coordinator(email):
        return True
    if not ward_id:
        return False
    return ward_id in wards_for(email)


def _kind(req) -> str:
    return {"medical": "medical", "food": "food", "shelter": "shelter"}.get(req.type.value, "boat")


def _expired(match) -> bool:
    if match.hold_expired:
        return True
    if match.state != MatchState.PROPOSED or not match.hold_expires_at:
        return False
    try:
        when = datetime.fromisoformat(match.hold_expires_at)
    except ValueError:
        return False
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) < when:
        return False
    storage_service.release_hold(match.resource_id, actor="dispatcher")
    match.hold_expired = True
    storage_service.save_match(match, actor="dispatcher")
    return True


def _why(req) -> str | None:
    if req is None:
        return None
    for step in req.trace or []:
        if step.get("agent") == "Explainer" and step.get("output"):
            return str(step["output"])
    return None


def _row(match, expired: bool) -> dict:
    req = storage_service.get_request(match.request_id)
    res = storage_service.get_resource(match.resource_id)
    title = None
    ward = None
    if req is not None:
        title = req.place_text or req.summary or req.id
        ward = req.ward_id
    return {
        "match_id": match.id,
        "request_id": match.request_id,
        "resource_id": match.resource_id,
        "title": title or match.request_id,
        "team_name": res.name if res else None,
        "team_kind": res.kind.value if res else None,
        "why": _why(req) or match.explanation,
        "expires_at": match.hold_expires_at,
        "expired": expired,
        "ward_id": ward,
        "dispatched": False,
    }


def shortages_for(email: str) -> List[dict]:
    return list(_LAST_SHORTAGES.get(email, []))


def scoped_proposals(email: str) -> List[dict]:
    rows = []
    for match in storage_service.list_matches():
        if match.state != MatchState.PROPOSED:
            continue
        req = storage_service.get_request(match.request_id)
        if req is None or not visible_to(email, req.ward_id):
            continue
        rows.append(_row(match, _expired(match)))
    return rows


def plan_for(email: str) -> dict:
    wards = wards_for(email)
    cases = [
        req for req in storage_service.list_requests()
        if not req.merged_into and req.status not in CLOSED and visible_to(email, req.ward_id)
    ]
    held = {row["request_id"] for row in scoped_proposals(email) if not row["expired"]}
    need: Dict[str, int] = {}
    have: Dict[str, int] = {}
    failures: List[dict] = []
    for req in cases:
        kind = _kind(req)
        need[kind] = need.get(kind, 0) + 1
        if req.id in held:
            have[kind] = have.get(kind, 0) + 1
            continue
        teams = find_teams(kind)
        if not teams:
            failures.append({
                "kind": kind,
                "explanation": "Not enough teams for the demand. No free team of this kind.",
            })
            continue
        result = propose_assignment(req.id, teams[0]["id"])
        if not result.get("ok"):
            failures.append({"kind": kind, "explanation": str(result.get("explanation") or "")})
            continue
        match = storage_service.get_match(result["match_id"])
        if match is not None:
            match.hold_expires_at = (datetime.now(timezone.utc) + HOLD).isoformat()
            storage_service.save_match(match, actor="dispatcher")
        have[kind] = have.get(kind, 0) + 1
        if req.status in (RequestStatus.DISPATCHED, RequestStatus.APPROVED):
            raise RuntimeError("assist plan dispatched a case")
    shortages = []
    seen = set()
    for item in failures:
        kind = item["kind"]
        if kind in seen or not item.get("explanation"):
            continue
        if need.get(kind, 0) > have.get(kind, 0):
            shortages.append({
                "kind": kind,
                "have": have.get(kind, 0),
                "need": need.get(kind, 0),
                "explanation": item["explanation"],
            })
            seen.add(kind)
    _LAST_SHORTAGES[email] = shortages
    return {
        "proposals": scoped_proposals(email),
        "shortages": shortages,
        "wards": sorted(wards),
    }


@router.get("/proposals")
def list_proposals(user: CoordinatorUser = Depends(get_current_coordinator)):
    return {
        "proposals": scoped_proposals(user.email),
        "shortages": shortages_for(user.email),
        "wards": sorted(wards_for(user.email)),
    }


@router.post("/plan")
def run_plan(user: CoordinatorUser = Depends(get_current_coordinator)):
    return plan_for(user.email)
