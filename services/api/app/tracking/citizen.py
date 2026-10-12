"""Citizen view of the one assigned team. No other teams, no personal details, no position outside the window."""
from __future__ import annotations

from typing import Optional

from app.models.firestore_models import RequestStatus, StoredReport
from app.tools.geo import haversine_distance
from app.tools.storage import storage_service
from app.tracking.availability import TrackingError, position_stale
from app.tracking.live import live_eta

_SHOW = {RequestStatus.DISPATCHED, RequestStatus.IN_PROGRESS}
_DONE = {RequestStatus.COMPLETED, RequestStatus.RESOLVED, RequestStatus.CLOSED}


def citizen_tracking(report_id: str, token: Optional[str]) -> dict:
    if not token:
        raise TrackingError("bad_token", "Status token required")
    report: Optional[StoredReport] = storage_service.get_report(report_id)
    if report is None:
        raise TrackingError("not_found", "Report not found")
    if token != report.status_token:
        raise TrackingError("bad_token", "Status token does not match this report")

    req = storage_service.get_request(report.request_id) if report.request_id else None
    hidden = {
        "visible": False,
        "state": "hidden",
        "team_name": None,
        "team_kind": None,
        "distance_km": None,
        "eta_minutes": None,
        "no_nearby": False,
        "lat": None,
        "lng": None,
        "case_lat": None,
        "case_lng": None,
        "updated_at": None,
        "simulated": False,
        "stale": False,
        "trail": [],
    }
    if req is None or req.status not in _SHOW | _DONE:
        return hidden

    res = storage_service.get_resource(req.assigned_resource_id) if req.assigned_resource_id else None
    if req.status in _DONE:
        return {
            **hidden,
            "visible": True,
            "state": "completed",
            "team_name": res.name if res else None,
            "team_kind": res.kind.value if res else None,
        }

    state = "arrived" if req.status == RequestStatus.IN_PROGRESS else "dispatched"
    if res is None:
        return {**hidden, "visible": True, "state": state}

    distance = None
    eta = None
    no_nearby = False
    if req.lat is not None and req.lng is not None:
        distance = round(haversine_distance(res.lat, res.lng, req.lat, req.lng), 1)
        eta, no_nearby = live_eta(distance, res.kind.value)
    trail = [{"lat": point.lat, "lng": point.lng} for point in res.location_trail[-20:]]
    return {
        "visible": True,
        "state": state,
        "team_name": res.name,
        "team_kind": res.kind.value,
        "distance_km": distance,
        "eta_minutes": None if state == "arrived" else eta,
        "no_nearby": no_nearby,
        "lat": res.lat,
        "lng": res.lng,
        "case_lat": req.lat,
        "case_lng": req.lng,
        "updated_at": res.location_updated_at,
        "simulated": bool(res.simulated) or res.location_source == "simulated",
        "stale": position_stale(res),
        "trail": trail,
    }
