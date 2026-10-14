"""In-process event bus for the desk and the reporter status page."""

from __future__ import annotations

import asyncio
import queue
import threading
from typing import Any, Optional

# Audit action -> SSE event name. Heartbeats are sent by the stream, not the bus.
ACTION_KIND = {
    "request_created": "case.created",
    "request_saved": "case.updated",
    "status_change": "case.updated",
    "cluster_created": "case.merged",
    "cluster_split": "case.updated",
    "match_approved": "dispatch.created",
    "resource_saved": "team.updated",
    "resource_created": "team.updated",
    "capacity_reserved": "team.updated",
    "capacity_released": "team.updated",
    "supplies_consumed": "team.updated",
    "location_update": "team.updated",
    "team_confirm": "team.updated",
}

HEARTBEAT_SECONDS = 15

_lock = threading.Lock()
_subscribers: list[Any] = []
_seen_alerts: Optional[set[str]] = None


class LoopBox:
    """A subscriber that lives on the event loop.

    An SSE stream waits on this without holding a worker thread, so many open or stale
    streams cannot starve the one phone that is waiting for "A team is on the way".
    """

    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=200)

    def put_nowait(self, event: dict[str, Any]) -> None:
        self.loop.call_soon_threadsafe(self._put, event)

    def _put(self, event: dict[str, Any]) -> None:
        try:
            self.queue.put_nowait(event)
        except asyncio.QueueFull:
            pass

    async def get(self, timeout: float) -> dict[str, Any]:
        return await asyncio.wait_for(self.queue.get(), timeout)


def subscribe() -> queue.Queue:
    box: queue.Queue = queue.Queue(maxsize=200)
    with _lock:
        _subscribers.append(box)
    return box


def subscribe_async() -> LoopBox:
    box = LoopBox(asyncio.get_running_loop())
    with _lock:
        _subscribers.append(box)
    return box


def unsubscribe(box: Any) -> None:
    with _lock:
        if box in _subscribers:
            _subscribers.remove(box)


def publish(event: dict[str, Any]) -> None:
    with _lock:
        targets = list(_subscribers)
    for box in targets:
        try:
            box.put_nowait(event)
        except queue.Full:
            # A slow client should not stall intake. It will catch up on the next poll.
            pass
        except RuntimeError:
            # The stream's event loop has closed. Its generator removes the box on exit.
            pass


def emit_audit(action: str, target: str, after: Optional[dict[str, Any]]) -> None:
    kind = ACTION_KIND.get(action)
    if not kind:
        return
    body = after or {}
    request_id = body.get("request_id")
    if kind.startswith("case.") and not request_id:
        request_id = target
    if action == "match_approved":
        request_id = body.get("request_id")
    request_ids = [str(item) for item in (body.get("request_ids") or []) if item]
    if request_id and str(request_id) not in request_ids:
        request_ids.append(str(request_id))
    publish({
        "type": kind,
        "id": target,
        "request_id": request_id,
        "request_ids": request_ids,
    })
    if kind in {"case.created", "case.merged", "case.updated", "dispatch.created"}:
        emit_new_alerts()


def emit_new_alerts() -> None:
    """Publish alert.created for ids that were not present on the previous check."""
    global _seen_alerts
    try:
        from app.tools.anomaly import collect_alerts
        from app.tools.storage import storage_service
        current = {alert.id for alert in collect_alerts(storage_service)}
    except Exception:
        return
    if _seen_alerts is None:
        _seen_alerts = current
        return
    for alert_id in sorted(current - _seen_alerts):
        publish({"type": "alert.created", "id": alert_id, "request_id": None, "request_ids": []})
    _seen_alerts = current


def reset_for_tests() -> None:
    global _seen_alerts
    with _lock:
        _subscribers.clear()
    _seen_alerts = None
