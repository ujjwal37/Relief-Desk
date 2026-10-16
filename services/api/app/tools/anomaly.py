"""Deterministic anomaly rules. Flags only; nothing is deleted."""
from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List, Optional

import yaml
from pydantic import BaseModel

ACKNOWLEDGED: set[str] = set()


class AnomalyAlert(BaseModel):
    id: str
    kind: str
    title: str
    reason: str
    ward_id: Optional[str] = None
    severity: str = "high"
    age_label: str = "just now"
    detected_at: Optional[str] = None
    acknowledged: bool = False


def spike_alerts(ward_counts: Dict[str, int], baseline: int, window: str = "20 min") -> List[AnomalyAlert]:
    alerts: List[AnomalyAlert] = []
    floor = max(1, baseline)
    for ward, count in sorted(ward_counts.items()):
        if count >= floor * 3:
            alerts.append(AnomalyAlert(
                id=f"spike-{ward}",
                kind="spike",
                title="Report spike",
                reason=f"{ward}: {count} reports in {window} (baseline {floor})",
                ward_id=ward,
                severity="critical",
                age_label="4 min ago",
            ))
    return alerts


def silent_zone_alerts(
    ward_counts: Dict[str, int],
    neighbour_counts: Dict[str, int],
    window: str = "3 h",
) -> List[AnomalyAlert]:
    alerts: List[AnomalyAlert] = []
    for ward, count in sorted(ward_counts.items()):
        neighbours = neighbour_counts.get(ward, 0)
        if count == 0 and neighbours > 0:
            alerts.append(AnomalyAlert(
                id=f"silent-{ward}",
                kind="silent_zone",
                title="Silent zone",
                reason=f"{ward}: 0 reports in {window}, neighbours rising. Possible outage.",
                ward_id=ward,
                severity="high",
                age_label="11 min ago",
            ))
    return alerts


def resource_gap_alerts(demand_by_kind: Dict[str, int], free_by_kind: Dict[str, int]) -> List[AnomalyAlert]:
    alerts: List[AnomalyAlert] = []
    for kind, demand in sorted(demand_by_kind.items()):
        free = int(free_by_kind.get(kind, 0))
        if demand > free:
            alerts.append(AnomalyAlert(
                id=f"gap-{kind}",
                kind="resource_gap",
                title="Resource gap",
                reason=f"{kind.capitalize()} demand {demand}, only {free} free",
                severity="high",
                age_label="17 min ago",
            ))
    return alerts


def conflict_alerts(pairs: Iterable[Dict[str, str]]) -> List[AnomalyAlert]:
    alerts: List[AnomalyAlert] = []
    for pair in pairs:
        left = (pair.get("statement_a") or "").strip()
        right = (pair.get("statement_b") or "").strip()
        ward = pair.get("ward_name") or pair.get("ward_id") or "the same area"
        if left and right and left.lower() != right.lower():
            alerts.append(AnomalyAlert(
                id=f"conflict-{ward}".replace(" ", "-").lower(),
                kind="conflict",
                title="Conflicting reports",
                reason=f"\"{left}\" vs \"{right}\" in {ward}",
                ward_id=pair.get("ward_id"),
                severity="medium",
                age_label="26 min ago",
            ))
    return alerts


def stale_alerts(ages_minutes: Iterable[float], threshold: int = 90) -> List[AnomalyAlert]:
    stale = [age for age in ages_minutes if age > threshold]
    if not stale:
        return []
    return [AnomalyAlert(
        id="stale-open",
        kind="stale",
        title="Stale requests",
        reason=f"{len(stale)} requests unconfirmed for {threshold} min → needs recheck",
        severity="medium",
        age_label="34 min ago",
    )]


def alerts_from_signals(signals: List[Dict[str, Any]]) -> List[AnomalyAlert]:
    alerts: List[AnomalyAlert] = []
    for signal in signals:
        kind = signal.get("kind")
        if kind == "spike":
            alerts.extend(spike_alerts(
                {signal["ward_name"]: int(signal["recent_reports"])},
                baseline=int(signal["baseline"]),
                window=signal.get("window") or "20 min",
            ))
        elif kind == "silent_zone":
            ward = signal.get("ward_name") or signal["ward_id"]
            alerts.extend(silent_zone_alerts(
                {ward: int(signal["recent_reports"])},
                {ward: int(signal.get("neighbour_reports") or 0)},
                window=signal.get("window") or "3 h",
            ))
        elif kind == "resource_gap":
            alerts.extend(resource_gap_alerts(
                {signal["resource_kind"]: int(signal["demand"])},
                {signal["resource_kind"]: int(signal["free"])},
            ))
        elif kind == "conflict":
            alerts.extend(conflict_alerts([signal]))
        elif kind == "stale":
            count = int(signal.get("count") or 0)
            age = float(signal.get("age_minutes") or 0)
            alerts.extend(stale_alerts([age] * count, threshold=90))
    return alerts


def load_seed_signals() -> List[Dict[str, Any]]:
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
    path = os.path.join(base_dir, "data", "synthetic", "flood_v1", "anomaly_signals.yaml")
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return list(data.get("signals") or [])


SPIKE_WINDOW_MIN = 20
BASELINE_WINDOW_MIN = 180
# A ward needs at least this many distinct cases in the window, and 3x its usual rate, to be a spike.
SPIKE_MIN_CASES = 4
SPIKE_FACTOR = 3.0
STALE_MIN = 90
OPEN_STATUSES = ("new", "needs_recheck", "matched")


def _parse(stamp: Optional[str]):
    from datetime import datetime, timezone

    if not stamp:
        return None
    try:
        value = datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


def age_label_for(detected_at: Optional[str], now=None) -> str:
    from datetime import datetime, timezone

    when = _parse(detected_at)
    if when is None:
        return "just now"
    now = now or datetime.now(timezone.utc)
    minutes = max(0, int((now - when).total_seconds() // 60))
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes} min ago"
    return f"{minutes // 60} h ago"


def _status(item) -> str:
    return str(getattr(item.status, "value", item.status))


def live_alerts_from_storage(storage) -> List[AnomalyAlert]:
    """Alerts from the live case store. Ages come from real timestamps, never fixed labels."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    requests = [req for req in storage.list_requests() if not req.merged_into]
    alerts: List[AnomalyAlert] = []

    # Spike: distinct cases (merged copies excluded) in the last 20 min vs the ward's own rate
    # over the 3 hours before that.
    recent: Dict[str, List[str]] = {}
    prior: Dict[str, int] = {}
    for req in requests:
        when = _parse(req.created_at)
        if when is None or not req.ward_id:
            continue
        minutes = (now - when).total_seconds() / 60.0
        if minutes <= SPIKE_WINDOW_MIN:
            recent.setdefault(req.ward_id, []).append(req.created_at)
        elif minutes <= SPIKE_WINDOW_MIN + BASELINE_WINDOW_MIN:
            prior[req.ward_id] = prior.get(req.ward_id, 0) + 1
    slots = BASELINE_WINDOW_MIN / SPIKE_WINDOW_MIN
    for ward, stamps in sorted(recent.items()):
        usual = prior.get(ward, 0) / slots
        needed = max(SPIKE_MIN_CASES, SPIKE_FACTOR * usual)
        if len(stamps) >= needed:
            first = min(stamps)
            alerts.append(AnomalyAlert(
                id=f"spike-{ward}",
                kind="spike",
                title="Report spike",
                reason=f"{ward}: {len(stamps)} new cases in {SPIKE_WINDOW_MIN} min (usual {usual:.1f} per {SPIKE_WINDOW_MIN} min)",
                ward_id=ward,
                severity="critical",
                detected_at=first,
            ))

    # Resource gap: open cases of a kind vs free teams of that kind (cases vs teams, same unit).
    kind_map = {"medical": "medical", "rescue": "boat", "food": "food", "shelter": "shelter", "animal_attack": "medical"}
    demand: Dict[str, List[str]] = {}
    for req in requests:
        kind = kind_map.get(str(getattr(req.type, "value", req.type)))
        if kind and _status(req) in OPEN_STATUSES and "hoax" not in (req.flags or []):
            demand.setdefault(kind, []).append(req.created_at)
    free_teams: Dict[str, int] = {}
    for resource in storage.list_resources():
        if _status(resource) == "available" and resource.capacity_remaining > 0 and not resource.hold_request_id:
            key = str(getattr(resource.kind, "value", resource.kind))
            free_teams[key] = free_teams.get(key, 0) + 1
    for kind, stamps in sorted(demand.items()):
        free = free_teams.get(kind, 0)
        if len(stamps) > free:
            reason = (f"No {kind} team free. {len(stamps)} open cases are waiting."
                      if free == 0 else f"{kind.capitalize()}: {len(stamps)} open cases, only {free} free teams")
            alerts.append(AnomalyAlert(
                id=f"gap-{kind}",
                kind="resource_gap",
                title="Resource gap",
                reason=reason,
                severity="high",
                detected_at=min((s for s in stamps if s), default=None),
            ))

    conflicts = [req for req in requests if "conflict" in (req.flags or [])]
    if conflicts:
        alerts.append(AnomalyAlert(
            id="conflict-live",
            kind="conflict",
            title="Conflicting reports",
            reason=f"{len(conflicts)} cases have reports that disagree on the hazard. Flagged, not deleted.",
            severity="medium",
            detected_at=max((req.updated_at or req.created_at) for req in conflicts),
        ))

    stale = []
    for req in requests:
        when = _parse(req.created_at)
        if when is None or _status(req) not in OPEN_STATUSES:
            continue
        if (now - when).total_seconds() / 60.0 > STALE_MIN:
            stale.append(req.created_at)
    if stale:
        alerts.append(AnomalyAlert(
            id="stale-open",
            kind="stale",
            title="Stale requests",
            reason=f"{len(stale)} open cases waiting over {STALE_MIN} min without a team",
            severity="medium",
            # The alert started when the oldest case crossed the threshold.
            detected_at=(_parse(min(stale)) + __import__("datetime").timedelta(minutes=STALE_MIN)).isoformat(),
        ))
    for alert in alerts:
        alert.age_label = age_label_for(alert.detected_at, now)
    return alerts


def _gap_kind(alert_id: str) -> str:
    return alert_id.removeprefix("gap-none-").removeprefix("gap-")


def collect_alerts(storage=None) -> List[AnomalyAlert]:
    """Live alerts first. Seeded scenario alerts are always labelled Sample and never replace a live one."""
    live = live_alerts_from_storage(storage) if storage is not None else []
    live_keys = {(alert.kind, alert.ward_id or alert.id) for alert in live}
    live_gap_kinds = {_gap_kind(alert.id) for alert in live if alert.kind == "resource_gap"}
    merged: Dict[str, AnomalyAlert] = {}
    for alert in live:
        merged[alert.id] = alert
    from datetime import datetime, timezone, timedelta
    now_dt = datetime.now(timezone.utc)
    mins_map = {"spike": 4, "silent_zone": 11, "resource_gap": 17, "conflict": 26, "stale": 42}
    for alert in alerts_from_signals(load_seed_signals()):
        if alert.kind == "resource_gap" and _gap_kind(alert.id) in live_gap_kinds:
            continue
        if (alert.kind, alert.ward_id or alert.id) in live_keys:
            continue
        m = mins_map.get(alert.kind, 11)
        det_time = (now_dt - timedelta(minutes=m)).isoformat()
        sample = alert.model_copy(update={
            "id": f"sample-{alert.id}",
            "title": f"Sample: {alert.title}",
            "reason": f"Sample scenario. {alert.reason}",
            "age_label": f"{m} min ago",
            "detected_at": det_time,
            "severity": "medium" if alert.severity == "critical" else alert.severity,
        })
        merged.setdefault(sample.id, sample)
    result = []
    for alert in merged.values():
        alert.acknowledged = alert.id in ACKNOWLEDGED
        result.append(alert)
    return result


def acknowledge(alert_id: str) -> bool:
    ACKNOWLEDGED.add(alert_id)
    return True
