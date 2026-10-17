"""Command, Situation (and its brief), Alerts and Teams count with one rule."""
from fastapi.testclient import TestClient

from app.agents.sitrep import collect_counts
from app.main import app
from app.tools.desk_counts import free_by_kind, is_waiting
from app.tools.storage import storage_service

client = TestClient(app)
AUTH = {"Authorization": "Bearer demo-coordinator-token"}


def _waiting_like_command(rows):
    closed = {"dispatched", "completed", "accepted", "en_route", "in_progress", "on_scene", "cancelled"}
    return [r for r in rows if r["status"] not in closed and not r.get("merged_into")
            and not ({"info_closed", "dismissed_hoax"} & set(r.get("flags") or []))]


def test_waiting_and_free_teams_agree_across_screens():
    storage_service.load_full_scenario()
    boats = [r for r in storage_service.list_resources() if str(getattr(r.kind, "value", r.kind)) == "boat"]
    for res in boats[1:]:
        res.assigned_request_id = "INC-007"  # every boat but one is busy, so Alerts shows a gap
    try:
        rows = client.get("/api/requests", headers=AUTH).json()
        counts = collect_counts()
        assert counts.pending == len(_waiting_like_command(rows))
        assert counts.pending == sum(1 for r in storage_service.list_requests() if is_waiting(r))
        free = free_by_kind(storage_service.list_resources())
        assert counts.free_boats == free.get("boat", 0)
        assert counts.free_medical == free.get("medical", 0)
        alerts = client.get("/api/alerts", headers=AUTH).json()
        gap = next(a for a in alerts if a["id"] == "gap-boat")
        assert f"only {counts.free_boats} free" in gap["reason"] or (counts.free_boats == 0 and "No boat team free" in gap["reason"])
        assert f"{counts.rescue_open} open cases" in gap["reason"]
        brief = client.post("/api/sitrep", headers=AUTH).json()["brief"]
        assert str(counts.pending) in brief
        assert len([line for line in brief.splitlines() if line.strip()]) <= 3
    finally:
        storage_service.load_full_scenario()
