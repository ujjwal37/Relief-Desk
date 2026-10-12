"""Live locations, team status, and the citizen tracking card."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.auth import CoordinatorUser, get_current_coordinator
from app.config import settings
from app.models.firestore_models import StoredResource
from app.tools.storage import storage_service
from app.tracking.availability import TrackingError, apply_team_action, override_status
from app.tracking.citizen import citizen_tracking
from app.tracking.live import ingest_fix, list_snapshots
from app.tracking.simulate import step_all
from app.tracking.tokens import team_share_token, token_matches

logger = logging.getLogger("relief_desk.tracking")
router = APIRouter(prefix="/api", tags=["Live tracking"])

_HTTP = {
    "not_found": status.HTTP_404_NOT_FOUND,
    "bad_token": status.HTTP_401_UNAUTHORIZED,
    "rate_limit": status.HTTP_429_TOO_MANY_REQUESTS,
    "impossible_jump": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "bad_transition": status.HTTP_400_BAD_REQUEST,
    "demo_off": status.HTTP_403_FORBIDDEN,
}


class FixBody(BaseModel):
    lat: float
    lng: float
    accuracy: Optional[float] = None
    heading: Optional[float] = None
    speed: Optional[float] = None
    ts: Optional[str] = None
    token: Optional[str] = None


class StatusBody(BaseModel):
    action: str
    token: Optional[str] = None
    people_helped: Optional[int] = Field(default=None, ge=0, le=500)
    needs_follow_up: Optional[bool] = None


class OverrideBody(BaseModel):
    status: str
    reason: str = Field(min_length=3, max_length=240)


def _http(exc: TrackingError) -> HTTPException:
    code = _HTTP.get(exc.code, status.HTTP_400_BAD_REQUEST)
    headers = {"Retry-After": "4"} if exc.code == "rate_limit" else None
    return HTTPException(status_code=code, detail=str(exc), headers=headers)


def _require_team_token(resource_id: str, supplied: Optional[str]) -> None:
    if storage_service.get_resource(resource_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    if not token_matches(resource_id, supplied):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Team token required")


@router.get("/teams/locations")
def team_locations(user: CoordinatorUser = Depends(get_current_coordinator)):
    try:
        logger.info("Coordinator %s listed live team locations", user.email)
        return {"teams": list_snapshots()}
    except Exception as exc:
        logger.exception("Failed to list team locations: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


@router.post("/teams/{team_id}/location", response_model=StoredResource)
def post_team_location(
    team_id: str,
    body: FixBody,
    token: Optional[str] = Query(None),
    x_team_token: Optional[str] = Header(None),
):
    supplied = token or body.token or x_team_token
    _require_team_token(team_id, supplied)
    try:
        return ingest_fix(
            team_id,
            body.lat,
            body.lng,
            accuracy=body.accuracy,
            heading=body.heading,
            speed=body.speed,
            ts=body.ts,
            source="gps",
        )
    except TrackingError as exc:
        raise _http(exc)
    except Exception as exc:
        logger.exception("Location update failed for %s: %s", team_id, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


@router.post("/teams/{team_id}/status", response_model=StoredResource)
def post_team_status(
    team_id: str,
    body: StatusBody,
    token: Optional[str] = Query(None),
    x_team_token: Optional[str] = Header(None),
):
    supplied = token or body.token or x_team_token
    _require_team_token(team_id, supplied)
    try:
        return apply_team_action(
            team_id,
            body.action,
            actor="team",
            people_helped=body.people_helped,
            needs_follow_up=body.needs_follow_up,
        )
    except TrackingError as exc:
        raise _http(exc)
    except Exception as exc:
        logger.exception("Team status failed for %s: %s", team_id, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


@router.post("/teams/{team_id}/override", response_model=StoredResource)
def post_override(
    team_id: str,
    body: OverrideBody,
    user: CoordinatorUser = Depends(get_current_coordinator),
):
    try:
        return override_status(team_id, body.status, body.reason, actor=user.email)
    except TrackingError as exc:
        raise _http(exc)
    except Exception as exc:
        logger.exception("Override failed for %s: %s", team_id, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


@router.get("/reports/{report_id}/tracking")
def get_citizen_tracking(report_id: str, token: Optional[str] = Query(None)):
    try:
        return citizen_tracking(report_id, token)
    except TrackingError as exc:
        raise _http(exc)
    except Exception as exc:
        logger.exception("Citizen tracking failed for %s: %s", report_id, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


@router.post("/demo/tracking/step")
def demo_step(user: CoordinatorUser = Depends(get_current_coordinator)):
    if not settings.DEMO_MODE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Simulated movement is only available in demo mode")
    try:
        logger.info("Coordinator %s stepped simulated movement", user.email)
        return {"teams": step_all(), "simulated": True}
    except Exception as exc:
        logger.exception("Demo step failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


def public_share_token(resource_id: str) -> str:
    return team_share_token(resource_id)
