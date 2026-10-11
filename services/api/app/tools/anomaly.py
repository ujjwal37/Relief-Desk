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


def live_alerts_from_storage(storage) -> List[AnomalyAlert]:
    requests = storage.list_requests()
    counts: Dict[str, int] = {}
    for req in requests:
        if req.ward_id:
            counts[req.ward_id] = counts.get(req.ward_id, 0) + 1
    alerts: List[AnomalyAlert] = []
    if counts:
        baseline = max(1, sorted(counts.values())[len(counts) // 2])
        alerts.extend(spike_alerts(counts, baseline=baseline))

    demand: Dict[str, int] = {}
    for req in requests:
        if req.status.value in ("resolved", "closed"):
            continue
        demand[req.type.value] = demand.get(req.type.value, 0) + 1
    free: Dict[str, int] = {}
    for resource in storage.list_resources():
        free[resource.kind.value] = free.get(resource.kind.value, 0) + int(resource.capacity_remaining)
    # Map incident types onto resource kinds we actually stock.
    kind_map = {"medical": "medical", "rescue": "boat", "food": "food", "shelter": "shelter"}
    mapped_demand = {kind_map[k]: v for k, v in demand.items() if k in kind_map}
    alerts.extend(resource_gap_alerts(mapped_demand, free))
    available_teams: Dict[str, int] = {}
    for resource in storage.list_resources():
        status = resource.status.value if hasattr(resource.status, "value") else str(resource.status)
        if status == "available" and resource.capacity_remaining > 0:
            available_teams[resource.kind.value] = available_teams.get(resource.kind.value, 0) + 1
    for kind, open_cases in mapped_demand.items():
        if open_cases > 0 and available_teams.get(kind, 0) == 0:
            alerts.append(AnomalyAlert(
                id=f"gap-none-{kind}",
                kind="resource_gap",
                title="Resource gap",
                reason=f"No {kind} team free. {open_cases} cases are still waiting.",
                severity="high",
                age_label="1 min ago",
            ))

    conflict_wards = [req for req in requests if "conflict" in (req.flags or [])]
    if conflict_wards:
        alerts.append(AnomalyAlert(
            id="conflict-live",
            kind="conflict",
            title="Conflicting reports",
            reason=f"{len(conflict_wards)} requests disagree on the hazard. Flagged, not deleted.",
            severity="medium",
            age_label="26 min ago",
        ))

    stale_ages = []
    for req in requests:
        if "stale" in (req.flags or []) or req.status.value == "needs_recheck":
            stale_ages.append(120)
    alerts.extend(stale_alerts(stale_ages, threshold=90))
    return alerts


def collect_alerts(storage=None) -> List[AnomalyAlert]:
    merged: Dict[str, AnomalyAlert] = {}
    for alert in alerts_from_signals(load_seed_signals()):
        merged[alert.id] = alert
    if storage is not None:
        for alert in live_alerts_from_storage(storage):
            merged.setdefault(alert.id, alert)
    result = []
    for alert in merged.values():
        alert.acknowledged = alert.id in ACKNOWLEDGED
        result.append(alert)
    return result


def acknowledge(alert_id: str) -> bool:
    ACKNOWLEDGED.add(alert_id)
    return True
