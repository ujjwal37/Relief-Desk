"""Live demo queue: eight real intake reports, one shared run, no invented Gemini calls."""
import threading

from fastapi.testclient import TestClient

from app.config import settings
from app.llm.pacer import judge_limit
from app.main import app
from app.tools import live_demo
from app.tools.storage import storage_service

client = TestClient(app)
AUTH = {"Authorization": "Bearer demo-coordinator-token"}


def _finish(monkeypatch):
    monkeypatch.setattr(settings, "DEMO_MODE", True)
    monkeypatch.setattr(settings, "AI_MODE", "fallback")
    monkeypatch.setattr(settings, "GEMINI_RPM", 0)
    judge_limit.reset()
    live_demo.reset_for_tests()
    storage_service.reset_demo()


def test_live_run_merges_duplicates_flags_hoax_and_ranks_the_critical_case(monkeypatch):
    _finish(monkeypatch)
    started = client.post("/api/demo/live-run", headers=AUTH)
    assert started.status_code == 200, started.text
    thread = live_demo._thread
    assert thread is not None
    thread.join(timeout=120)
    state = client.get("/api/demo/live-run", headers=AUTH).json()
    assert state["error"] is None, state
    assert state["status"] == "done"
    assert state["received"] == 8
    assert state["running"] is False

    rows = []
    for cid in state["case_ids"]:
        row = storage_service.get_request(cid)
        assert row is not None
        rows.append(row)
    temple = [row for row in rows if "chalakudy mahadeva temple" in (row.raw_text or "").lower() or "चालाकुडी" in (row.raw_text or "")]
    assert len(temple) == 3
    # 4 people and 6 people at the same temple stay separate. The Hindi report names no new count, so it joins one of them.
    four = next(row for row in temple if "4 people" in (row.raw_text or "").lower())
    six = next(row for row in temple if "6 people" in (row.raw_text or "").lower())
    assert not four.merged_into
    assert not six.merged_into
    assert not any(row.merged_into for row in temple)
    flagged = [row for row in temple if row.possible_duplicate and row.possible_duplicate.target_id]
    assert len(flagged) >= 1
    assert any(row.possible_duplicate.target_id in {four.id, six.id} for row in flagged)

    hoax = next(row for row in rows if "nasa announced" in (row.raw_text or "").lower() or "likely_hoax" in (row.flags or []))
    visible = storage_service.get_request(hoax.merged_into) if hoax.merged_into else hoax
    assert visible is not None
    assert "likely_hoax" in (visible.flags or []) or "hoax" in (visible.flags or [])
    assert visible.hoax_reason
    assert visible.urgency_score < 60

    critical = storage_service.get_request(state["critical_id"])
    assert critical is not None
    assert critical.urgency_score >= 80
    demo_scores = []
    for row in rows:
        shown = storage_service.get_request(row.merged_into) if row.merged_into else row
        if shown is not None:
            demo_scores.append(shown.urgency_score)
    assert critical.urgency_score == max(demo_scores)
    live_demo.reset_for_tests()
    storage_service.reset_demo()


def test_second_start_joins_the_run_in_progress():
    live_demo.reset_for_tests()
    gate = threading.Event()

    def submit(_sample):
        gate.wait(5)
        return {"request_id": "req_blocked"}

    first = live_demo.start(submit)
    try:
        assert first["running"] is True
        second = live_demo.start(submit)
        assert second["running"] is True
        assert second["received"] == first["received"]
    finally:
        gate.set()
        live_demo.reset_for_tests()


def test_own_report_is_refused_when_gemini_is_off_and_creates_no_case(monkeypatch):
    _finish(monkeypatch)
    before = {row.id for row in storage_service.list_requests()}
    response = client.post("/api/demo/own-report", headers=AUTH, json={"text": "Water is inside the house. Send a boat."})
    assert response.status_code == 429
    assert "free limit" in response.json()["detail"]
    after = {row.id for row in storage_service.list_requests()}
    assert after == before


def test_seed_trace_does_not_invent_a_model_or_a_dash_distance():
    storage_service.reset_demo()
    from app.agents.pipeline import ensure_trace

    row = next(item for item in storage_service.list_requests() if not item.merged_into)
    row.trace = None
    row.ai = None
    row.ai_source = "offline_fallback"
    ensure_trace(row)
    intake = next(step for step in row.trace or [] if step["agent"] == "Intake")
    matching = next(step for step in row.trace or [] if step["agent"] == "Matching")
    assert intake["provider"] == "fallback"
    assert not intake.get("model")
    assert intake.get("latency_ms") not in {1420, 1180, 1250, 1540}
    assert "prompt" in intake and intake["prompt"]
    recorded = {
        "agent": "Intake",
        "provider": "gemini",
        "model": "gemini-3.5-flash-lite",
        "latency_ms": 17188,
        "output": "People are trapped.",
        "tool_calls": [],
    }
    row.trace = [
        recorded,
        {"agent": "Triage", "provider": "gemini", "model": "gemini-3.5-flash-lite", "tool_calls": [], "output": "score 80"},
        {"agent": "Matching", "provider": "tool", "tool_calls": [], "output": "{}"},
    ]
    ensure_trace(row)
    assert recorded["prompt"]
    assert "No model ran" not in recorded["prompt"]
    assert row.trace[1]["tool_calls"] == ["score_urgency"]
    assert row.trace[2]["tool_calls"] == ["check_capacity", "match_score"]
    assert row.trace[2]["prompt"]
    assert matching["provider"] == "tool"
    assert matching["provider_label"] == "Google Maps"
    assert "—" not in (matching.get("output") or "")
    assert "Boat Alpha" not in (matching.get("output") or "")
