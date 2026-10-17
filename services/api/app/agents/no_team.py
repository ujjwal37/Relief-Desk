"""No free team of the right kind: say why, and offer the coordinator four honest options.

Nothing here dispatches. The coordinator picks an option; the choice is logged.
"""
from typing import List, Optional

from app.agents.matching import (
    BOAT_KMH, BOAT_MAX_KM, LAND_KMH, NEARBY_KM, _PRIMARY, _finish_minutes, travel_mode_for,
)
from app.models.firestore_models import ResourceStatus, StoredRequest, StoredResource
from app.tools.geo import haversine_distance

OPTIONS = ("reserve", "road", "wider", "escalate")


def _km(req: StoredRequest, res: StoredResource) -> Optional[float]:
    if req.lat is None or req.lng is None or res.lat is None or res.lng is None:
        return None
    return round(haversine_distance(req.lat, req.lng, res.lat, res.lng), 2)


def _eta(km: Optional[float], res: StoredResource) -> Optional[int]:
    if km is None:
        return None
    speed = BOAT_KMH if travel_mode_for(res) == "water" else LAND_KMH
    return max(1, round(km / speed * 60))


def no_team_options(req: StoredRequest, resources: List[StoredResource]) -> dict:
    kinds = _PRIMARY.get(req.type, [])
    right = [r for r in resources if r.kind in kinds]
    free = [r for r in right if r.status == ResourceStatus.AVAILABLE and (r.capacity_remaining or 0) > 0]
    busy = [r for r in right if r.status != ResourceStatus.AVAILABLE]
    need = req.people_count or 0
    limit = BOAT_MAX_KM if any(k.value == "boat" for k in kinds) else NEARBY_KM

    reason, detail = "none_of_kind", {}
    far = sorted([(r, _km(req, r)) for r in free if _km(req, r) is not None], key=lambda x: x[1])
    if not right:
        reason = "none_of_kind"
    elif far and far[0][1] > limit:
        reason, detail = "too_far", {"km": far[0][1], "limit": limit, "team": far[0][0].name}
    elif free and need and all((r.capacity_remaining or 0) < need for r in free):
        best = max(free, key=lambda r: r.capacity_remaining or 0)
        reason, detail = "too_small", {"seats": best.capacity_remaining, "need": need, "team": best.name}
    elif busy and not free:
        reason, detail = "all_busy", {"busy": len(busy)}

    reserve = None
    if busy:
        nearest = min(busy, key=lambda r: _km(req, r) if _km(req, r) is not None else 1e9)
        km = _km(req, nearest)
        wait = _finish_minutes(nearest)
        travel = _eta(km, nearest)
        reserve = {"team_id": nearest.id, "team": nearest.name, "job": nearest.assigned_request_id,
                   "free_in_min": wait, "eta_min": (wait + travel) if travel is not None else None, "km": km}

    road = None
    others = [r for r in resources if r.kind not in kinds and r.status == ResourceStatus.AVAILABLE
              and travel_mode_for(r) != "water" and (r.capacity_remaining or 0) > 0]
    if others:
        best = min(others, key=lambda r: _km(req, r) if _km(req, r) is not None else 1e9)
        km = _km(req, best)
        road = {"team_id": best.id, "team": best.name, "kind": best.kind.value, "km": km, "eta_min": _eta(km, best)}

    wider = None
    if far:
        res, km = far[0]
        wider = {"team_id": res.id, "team": res.name, "km": km, "eta_min": _eta(km, res)}

    return {"request_id": req.id, "reason": reason, "detail": detail, "limit_km": limit,
            "kind": kinds[0].value if kinds else None,
            "options": {"reserve": reserve, "road": road, "wider": wider, "escalate": {"available": True}}}