"""Who can take a case, and the field status loop. Numbers stay in this module."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from app.models.firestore_models import RequestStatus, ResourceStatus, StoredResource
from app.tools.storage import storage_service

STALE_AFTER_S = 120
CHECK_IN_AFTER_S = 10 * 60
SOON_FREE_AFTER_S = 8 * 60
IST = timezone(timedelta(hours=5, minutes=30))

BUSY_STATUSES = {
    ResourceStatus.BUSY,
    ResourceStatus.DISPATCHED,
    ResourceStatus.ACCEPTED,
    ResourceStatus.EN_ROUTE,
    ResourceStatus.ON_SCENE,
    ResourceStatus.RETURNING,
}

_NEXT = {
    "accept": ({ResourceStatus.DISPATCHED, ResourceStatus.BUSY}, ResourceStatus.ACCEPTED),
    "on_the_way": ({ResourceStatus.ACCEPTED}, ResourceStatus.EN_ROUTE),
    "arrived": ({ResourceStatus.EN_ROUTE}, ResourceStatus.ON_SCENE),
    "off_duty": ({ResourceStatus.AVAILABLE}, ResourceStatus.OFF_DUTY),
    "free": ({ResourceStatus.OFF_DUTY}, ResourceStatus.AVAILABLE),
}

_OVERRIDE = {
    "available": ResourceStatus.AVAILABLE,
    "busy": ResourceStatus.BUSY,
    "dispatched": ResourceStatus.DISPATCHED,
    "accepted": ResourceStatus.ACCEPTED,
    "en_route": ResourceStatus.EN_ROUTE,
    "on_scene": ResourceStatus.ON_SCENE,
    "returning": ResourceStatus.RETURNING,
    "off_duty": ResourceStatus.OFF_DUTY,
}


class TrackingError(Exception):
    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(detail)


def parse_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def age_seconds(stamp: Optional[str], now: datetime) -> Optional[float]:
    parsed = parse_ts(stamp)
    if parsed is None:
        return None
    return (now - parsed).total_seconds()


def clock_ist(stamp: Optional[str]) -> str:
    parsed = parse_ts(stamp) or datetime.now(timezone.utc)
    return parsed.astimezone(IST).strftime("%H:%M")


def position_fresh(res: StoredResource, now: Optional[datetime] = None) -> bool:
    """A seeded depot stays usable until the team shares a fix. A shared fix expires after 2 minutes."""
    now = now or datetime.now(timezone.utc)
    source = res.location_source or "seed"
    if source == "seed":
        return True
    age = age_seconds(res.location_updated_at, now)
    if age is None:
        return False
    return age <= STALE_AFTER_S


def position_stale(res: StoredResource, now: Optional[datetime] = None) -> bool:
    now = now or datetime.now(timezone.utc)
    if (res.location_source or "seed") == "seed":
        return False
    age = age_seconds(res.location_updated_at, now)
    return age is None or age > STALE_AFTER_S


def on_scene_seconds(res: StoredResource, now: datetime) -> float:
    age = age_seconds(res.status_changed_at or res.updated_at, now)
    return age if age is not None else 0.0


def candidate_kind(res: StoredResource, now: Optional[datetime] = None) -> Optional[str]:
    """free, soon_free, or None when the team must not be offered."""
    now = now or datetime.now(timezone.utc)
    if res.capacity_remaining <= 0 or res.status in (ResourceStatus.DEPLETED, ResourceStatus.OFF_DUTY):
        return None
    if not position_fresh(res, now):
        return None
    if res.status == ResourceStatus.AVAILABLE:
        return "free"
    if res.status == ResourceStatus.ON_SCENE and on_scene_seconds(res, now) >= SOON_FREE_AFTER_S:
        return "soon_free"
    return None


def proposal_block_reason(res: StoredResource, now: Optional[datetime] = None) -> Optional[str]:
    """Why a team cannot be proposed. Capacity is checked later, so a free team with no seats still reaches that check."""
    now = now or datetime.now(timezone.utc)
    if not position_fresh(res, now):
        return "stale"
    if res.status == ResourceStatus.OFF_DUTY:
        return "off_duty"
    if res.status == ResourceStatus.AVAILABLE:
        return None
    if res.status == ResourceStatus.ON_SCENE and on_scene_seconds(res, now) >= SOON_FREE_AFTER_S:
        return None
    return "busy"


def needs_check_in(res: StoredResource, now: Optional[datetime] = None) -> bool:
    """Busy, and neither the position nor the status has changed for 10 minutes."""
    now = now or datetime.now(timezone.utc)
    if res.status not in BUSY_STATUSES:
        return False
    ages = [
        age for age in (
            age_seconds(res.location_updated_at, now),
            age_seconds(res.status_changed_at, now),
        ) if age is not None
    ]
    if not ages:
        return True
    return min(ages) >= CHECK_IN_AFTER_S


def busy_minutes(res: StoredResource, now: Optional[datetime] = None) -> Optional[int]:
    if res.status not in BUSY_STATUSES or not res.busy_since:
        return None
    age = age_seconds(res.busy_since, now)
    if age is None:
        return None
    return max(0, int(age // 60))


def cite_sentence(res: StoredResource, distance_km: float, now: Optional[datetime] = None) -> str:
    seats = res.capacity_remaining
    if candidate_kind(res, now) == "soon_free":
        return f"{res.name} is finishing soon, {distance_km} km away, {seats} seats."
    clock = clock_ist(res.status_changed_at or res.updated_at or res.created_at)
    return f"{res.name} is free since {clock}, {distance_km} km away, {seats} seats."


def _touch_status(res: StoredResource, status: ResourceStatus, now: datetime) -> None:
    res.status = status
    res.status_changed_at = now.isoformat()
    res.updated_at = res.status_changed_at
    if status == ResourceStatus.AVAILABLE:
        res.busy_since = None
        res.assigned_request_id = None
    elif status in BUSY_STATUSES and not res.busy_since:
        res.busy_since = res.status_changed_at


def apply_team_action(
    resource_id: str,
    action: str,
    actor: str = "team",
    people_helped: Optional[int] = None,
    needs_follow_up: Optional[bool] = None,
) -> StoredResource:
    res = storage_service.get_resource(resource_id)
    if res is None:
        raise TrackingError("not_found", "Team not found")
    now = datetime.now(timezone.utc)
    before = res.model_dump()

    if action == "complete":
        return _complete(res, actor, people_helped, needs_follow_up, before, now)

    rule = _NEXT.get(action)
    if rule is None:
        raise TrackingError("bad_transition", "Unknown team action")
    allowed, target = rule
    if res.status not in allowed:
        raise TrackingError("bad_transition", f"Cannot {action} from {res.status.value}")

    if action == "arrived" and res.assigned_request_id:
        storage_service.mark_arrived(res.assigned_request_id, actor=actor, keep_position=True)
        res = storage_service.get_resource(resource_id)
        if res is None:
            raise TrackingError("not_found", "Team not found")
        from app.tracking.simulate import disarm
        disarm(resource_id)
    else:
        _touch_status(res, target, now)
        storage_service._resources[res.id] = res

    storage_service.record_audit(
        actor=actor,
        action="team_status",
        target=res.id,
        before={"status": before.get("status")},
        after={"action": action, "status": res.status.value},
    )
    return res


def _complete(
    res: StoredResource,
    actor: str,
    people_helped: Optional[int],
    needs_follow_up: Optional[bool],
    before: dict,
    now: datetime,
) -> StoredResource:
    if res.status != ResourceStatus.ON_SCENE:
        raise TrackingError("bad_transition", "Mark arrived before completing the case")
    if people_helped is None or needs_follow_up is None:
        raise TrackingError("bad_transition", "Completion needs people helped and a follow-up answer")
    if people_helped < 0 or people_helped > 500:
        raise TrackingError("bad_transition", "People helped must be between 0 and 500")

    lat, lng = res.lat, res.lng
    source = res.location_source
    request_id = res.assigned_request_id
    if request_id:
        storage_service.complete_request(request_id, actor=actor)
    res = storage_service.get_resource(res.id)
    if res is None:
        raise TrackingError("not_found", "Team not found")
    res.lat = lat
    res.lng = lng
    res.location_source = source or res.location_source
    res.status = ResourceStatus.AVAILABLE if res.capacity_remaining > 0 else ResourceStatus.DEPLETED
    res.assigned_request_id = None
    res.busy_since = None
    res.status_changed_at = now.isoformat()
    res.updated_at = res.status_changed_at
    storage_service._resources[res.id] = res
    from app.tracking.simulate import disarm
    disarm(res.id)
    outcome = {
        "action": "complete",
        "status": res.status.value,
        "people_helped": people_helped,
        "needs_follow_up": needs_follow_up,
        "lat": lat,
        "lng": lng,
    }
    storage_service.record_audit(
        actor=actor, action="team_complete", target=res.id, before={"status": before.get("status")}, after=outcome
    )
    if request_id:
        storage_service.record_audit(
            actor=actor, action="team_complete", target=request_id, before=None, after=outcome
        )
    return res


def override_status(resource_id: str, status: str, reason: str, actor: str) -> StoredResource:
    res = storage_service.get_resource(resource_id)
    if res is None:
        raise TrackingError("not_found", "Team not found")
    if status not in _OVERRIDE:
        raise TrackingError("bad_transition", "That status cannot be set")
    if not reason or len(reason.strip()) < 3:
        raise TrackingError("bad_transition", "An override needs a reason")
    now = datetime.now(timezone.utc)
    before_status = res.status.value
    request_id = res.assigned_request_id
    target = _OVERRIDE[status]
    if target == ResourceStatus.AVAILABLE and request_id:
        current = storage_service.get_request(request_id)
        if current and current.status in (
            RequestStatus.DISPATCHED, RequestStatus.APPROVED, RequestStatus.IN_PROGRESS
        ):
            try:
                storage_service.complete_request(request_id, actor=actor)
            except ValueError:
                pass
        res = storage_service.get_resource(resource_id) or res
    _touch_status(res, target, now)
    storage_service._resources[res.id] = res
    from app.tracking.simulate import disarm
    if target in (ResourceStatus.AVAILABLE, ResourceStatus.ON_SCENE, ResourceStatus.OFF_DUTY):
        disarm(res.id)
    storage_service.record_audit(
        actor=actor,
        action="team_override",
        target=res.id,
        before={"status": before_status},
        after={"status": res.status.value, "reason": reason.strip()},
    )
    return res
