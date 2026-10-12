"""Demo-only movement. Writes the same fix shape as a phone, and is always labelled simulated."""
from __future__ import annotations

import math
import threading
from dataclasses import dataclass

from app.config import settings
from app.models.firestore_models import ResourceStatus
from app.tools.storage import storage_service

_routes: dict[str, "Route"] = {}
_lock = threading.Lock()
_started = False


@dataclass
class Route:
    target_lat: float
    target_lng: float
    origin_lat: float
    origin_lng: float
    progress: float = 0.0


def disarm(resource_id: str) -> None:
    with _lock:
        _routes.pop(resource_id, None)


def disarm_all() -> None:
    with _lock:
        _routes.clear()


def arm_demo_route(resource_id: str, target_lat: float, target_lng: float) -> None:
    """Start a curved path toward the case. No-op when demo mode is off. Does not change status."""
    if not settings.DEMO_MODE:
        return
    res = storage_service.get_resource(resource_id)
    if res is None:
        return
    res.simulated = True
    res.location_source = "simulated"
    storage_service._resources[res.id] = res
    with _lock:
        _routes[resource_id] = Route(
            target_lat=target_lat,
            target_lng=target_lng,
            origin_lat=res.lat,
            origin_lng=res.lng,
        )
    _ensure_thread()


def _ensure_thread() -> None:
    global _started
    if _started:
        return
    _started = True

    def loop() -> None:
        while True:
            threading.Event().wait(3)
            if settings.DEMO_MODE:
                step_all()

    threading.Thread(target=loop, name="demo-tracking", daemon=True).start()


def step_all() -> list[dict]:
    from app.tracking.live import ingest_fix, team_snapshot

    with _lock:
        ids = list(_routes.keys())
    moved = []
    for resource_id in ids:
        res = storage_service.get_resource(resource_id)
        if res is None or res.status in (
            ResourceStatus.ON_SCENE,
            ResourceStatus.AVAILABLE,
            ResourceStatus.OFF_DUTY,
            ResourceStatus.RETURNING,
            ResourceStatus.DEPLETED,
        ):
            disarm(resource_id)
            continue
        with _lock:
            route = _routes.get(resource_id)
        if route is None:
            continue
        route.progress = min(0.9, route.progress + 0.12)
        lat, lng = _along(route)
        heading = _bearing(res.lat, res.lng, lat, lng)
        ingest_fix(
            resource_id,
            lat,
            lng,
            accuracy=12,
            heading=heading,
            speed=5.0,
            source="simulated",
            skip_rate=True,
            skip_jump=True,
        )
        current = storage_service.get_resource(resource_id)
        if current is not None:
            moved.append(team_snapshot(current))
    return moved


def _along(route: Route) -> tuple[float, float]:
    frac = route.progress
    lat = route.origin_lat + (route.target_lat - route.origin_lat) * frac
    lng = route.origin_lng + (route.target_lng - route.origin_lng) * frac
    bulge = math.sin(math.pi * frac) * 0.004
    dlat = route.target_lat - route.origin_lat
    dlng = route.target_lng - route.origin_lng
    lat += -dlng * bulge
    lng += dlat * bulge
    return lat, lng


def _bearing(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlam = math.radians(lng2 - lng1)
    y = math.sin(dlam) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlam)
    return round((math.degrees(math.atan2(y, x)) + 360.0) % 360.0, 1)
