from fastapi.testclient import TestClient

from app.main import app
from app.tools.anomaly import (
    conflict_alerts,
    resource_gap_alerts,
    silent_zone_alerts,
    spike_alerts,
    stale_alerts,
)

client = TestClient(app)
AUTH = {"Authorization": "Bearer demo-coordinator-token"}


def test_spike_and_silent_zone_rules():
    spike = spike_alerts({"Ward 7": 14}, baseline=3, window="20 min")
    assert len(spike) == 1
    assert "14 reports" in spike[0].reason
    assert "baseline 3" in spike[0].reason
    assert spike_alerts({"Ward 7": 4}, baseline=3) == []

    silent = silent_zone_alerts({"Ward 5": 0}, {"Ward 5": 6}, window="3 h")
    assert len(silent) == 1
    assert "0 reports" in silent[0].reason
    assert silent_zone_alerts({"Ward 5": 2}, {"Ward 5": 6}) == []


def test_gap_conflict_and_stale_rules():
    gap = resource_gap_alerts({"medical": 6}, {"medical": 2})
    assert "demand 6" in gap[0].reason
    assert resource_gap_alerts({"medical": 1}, {"medical": 4}) == []

    conflict = conflict_alerts([{
        "ward_name": "Ward 4",
        "statement_a": "Canal Road open",
        "statement_b": "blocked",
    }])
    assert "Canal Road open" in conflict[0].reason
    assert conflict_alerts([{"ward_name": "Ward 4", "statement_a": "open", "statement_b": "open"}]) == []

    stale = stale_alerts([120, 30, 200], threshold=90)
    assert stale[0].kind == "stale"
    assert stale[0].reason.startswith("2 requests")
    assert stale_alerts([10, 20], threshold=90) == []


def test_get_alerts_requires_coordinator_and_includes_seeded_spike_and_silent_zone():
    denied = client.get("/api/alerts")
    assert denied.status_code == 401

    response = client.get("/api/alerts", headers=AUTH)
    assert response.status_code == 200
    body = response.json()
    kinds = {item["kind"] for item in body}
    assert "spike" in kinds
    assert "silent_zone" in kinds
    spike = next(item for item in body if item["kind"] == "spike")
    silent = next(item for item in body if item["kind"] == "silent_zone")
    assert "14 reports" in spike["reason"]
    assert "0 reports" in silent["reason"]
    assert all(item["acknowledged"] is False or item["acknowledged"] is True for item in body)
