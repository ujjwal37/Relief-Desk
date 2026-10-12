"""Store a live fix, reject impossible jumps, and recompute ETA from that point."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.agents.matching import NEARBY_KM
from app.models.firestore_models import StoredRequest, StoredResource
from app.tools.geo import haversine_distance
from app.tools.storage import storage_service
from app.tracking.availability import (
    TrackingError,
    busy_minutes,
    candidate_kind,
    needs_check_in,
    parse_ts,
    position_stale,
)
from app.tracking.tokens import team_share_token

# Same 30 km cap as matching. Speeds are flood-road estimates, not the 20 km/h match card.
SPEED_KMH = {"boat": 18.0, "medical": 40.0, "food": 28.0, "shelter": 25.0}
MIN_INTERVAL_S = 4.0
_last_post: dict[str, float] = {}


def clear_rate_limits() -> None:
    _last_post.clear()


def live_eta(distance_km: float, kind: str) -> tuple[Optional[int], bool]:
    if distance_km > NEARBY_KM:
        return None, True
    speed = SPEED_KMH.get(kind, 20.0)
    return max(1, round((distance_km / speed) * 60)), False


def _max_kmh(kind: str) -> float:
    return SPEED_KMH.get(kind, 20.0) * 2.5


def ingest_fix(
    resource_id: str,
    lat: float,
    lng: float,
    accuracy: Optional[float] = None,
    heading: Optional[float] = None,
    speed: Optional[float] = None,
    ts: Optional[str] = None,
    source: str = "gps",
    skip_rate: bool = False,
    skip_jump: bool = False,
) -> StoredResource:
    res = storage_service.get_resource(resource_id)
    if res is None:
        raise TrackingError("not_found", "Team not found")
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise TrackingError("impossible_jump", "That point is not a valid location")
    if accuracy is not None and accuracy < 0:
        raise TrackingError("impossible_jump", "Accuracy cannot be negative")

    now_wall = time.monotonic()
    if not skip_rate:
        previous = _last_post.get(resource_id)
        if previous is not None and now_wall - previous < MIN_INTERVAL_S:
            raise TrackingError("rate_limit", "Location updates are limited to one every few seconds")

    new_ts = parse_ts(ts) or datetime.now(timezone.utc)
    if new_ts > datetime.now(timezone.utc) + timedelta(seconds=30):
        new_ts = datetime.now(timezone.utc)

    if not skip_jump and (res.location_source or "seed") == "gps" and source == "gps":
        _reject_jump(res, lat, lng, new_ts)

    res.lat = lat
    res.lng = lng
    res.accuracy_m = accuracy
    res.heading = heading
    res.speed_mps = speed
    res.location_source = source
    res.simulated = source == "simulated"
    res.location_updated_at = new_ts.isoformat()
    res.updated_at = res.location_updated_at
    storage_service._append_trail(res)
    storage_service._resources[res.id] = res
    if not skip_rate:
        _last_post[resource_id] = now_wall
    if source == "gps":
        from app.tracking.simulate import disarm
        disarm(resource_id)
    return res


def _reject_jump(res: StoredResource, lat: float, lng: float, new_ts: datetime) -> None:
    prev_ts = parse_ts(res.location_updated_at)
    if prev_ts is None:
        return
    elapsed = (new_ts - prev_ts).total_seconds()
    distance = haversine_distance(res.lat, res.lng, lat, lng)
    if elapsed <= 0:
        if distance > 0.05:
            raise TrackingError("impossible_jump", "That move is too fast for this team")
        return
    hours = elapsed / 3600.0
    if distance / hours > max(_max_kmh(res.kind.value), 80.0):
        raise TrackingError("impossible_jump", "That move is too fast for this team")


def _case_for(res: StoredResource) -> Optional[StoredRequest]:
    if not res.assigned_request_id:
        return None
    return storage_service.get_request(res.assigned_request_id)


def team_snapshot(res: StoredResource, now: Optional[datetime] = None) -> dict:
    now = now or datetime.now(timezone.utc)
    case = _case_for(res)
    distance = None
    eta = None
    no_nearby = False
    case_lat = case.lat if case else None
    case_lng = case.lng if case else None
    if case is not None and case.lat is not None and case.lng is not None:
        distance = haversine_distance(res.lat, res.lng, case.lat, case.lng)
        eta, no_nearby = live_eta(distance, res.kind.value)
    kind = candidate_kind(res, now)
    return {
        "id": res.id,
        "name": res.name,
        "kind": res.kind.value,
        "status": res.status.value,
        "lat": res.lat,
        "lng": res.lng,
        "heading": res.heading,
        "speed": res.speed_mps,
        "accuracy": res.accuracy_m,
        "updated_at": res.location_updated_at,
        "stale": position_stale(res, now),
        "simulated": bool(res.simulated) or res.location_source == "simulated",
        "source": res.location_source or "seed",
        "assigned_request_id": res.assigned_request_id,
        "case_lat": case_lat,
        "case_lng": case_lng,
        "distance_km": distance,
        "eta_minutes": eta,
        "no_nearby": no_nearby,
        "trail": [point.model_dump() for point in res.location_trail[-50:]],
        "check_in": needs_check_in(res, now),
        "busy_minutes": busy_minutes(res, now),
        "status_changed_at": res.status_changed_at,
        "busy_since": res.busy_since,
        "soon_free": kind == "soon_free",
        "share_token": team_share_token(res.id),
    }


def list_snapshots() -> list[dict]:
    return [team_snapshot(res) for res in storage_service.list_resources()]
