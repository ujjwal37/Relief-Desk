"""One definition of 'waiting case' and 'free team' for Command, Situation, Alerts, Teams and Ask.

Every screen and the Situation brief count with these two functions, so the numbers agree.
"""
from __future__ import annotations

from datetime import datetime, timezone

FRESH_MINUTES = 120
WAITING_STATUSES = ("new", "needs_recheck", "matched")
CLOSED_FLAGS = {"info_closed", "dismissed_hoax"}


def _value(x) -> str:
    return str(getattr(x, "value", x) or "")


def is_waiting(req) -> bool:
    """Same as the Command queue's Waiting tab: not sent, not closed, not a dismissed hoax or merged copy."""
    return (_value(req.status) in WAITING_STATUSES and not getattr(req, "merged_into", None)
            and not (CLOSED_FLAGS & set(req.flags or [])))


def checked_in_recently(res, now: datetime | None = None) -> bool:
    stamp = getattr(res, "location_updated_at", None)
    if not stamp:
        return False
    try:
        at = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return False
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    return ((now or datetime.now(timezone.utc)) - at).total_seconds() <= FRESH_MINUTES * 60


def is_free_team(res, now: datetime | None = None) -> bool:
    """Same as the Teams page 'Free': not on a case or hold, seats left, checked in within 2 h."""
    return (not getattr(res, "assigned_request_id", None) and not getattr(res, "hold_request_id", None)
            and _value(res.status) == "available" and (res.capacity_remaining or 0) > 0
            and checked_in_recently(res, now))


def free_by_kind(resources) -> dict:
    out: dict = {}
    for res in resources:
        if is_free_team(res):
            key = _value(res.kind)
            out[key] = out.get(key, 0) + 1
    return out
