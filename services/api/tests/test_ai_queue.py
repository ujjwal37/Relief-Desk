"""Model calls wait in a priority queue. A full queue is never a reason to fall back to rules."""
import threading
import time
import uuid

from fastapi.testclient import TestClient

from app.agents import desk_query
from app.config import settings
from app.llm.ai_queue import DESK, PrioritySlots, ai_priority, report_priority
from app.llm.client import llm_client
from app.main import app

client = TestClient(app)
AUTH = {"Authorization": "Bearer demo-coordinator-token"}


def _queue_behind(slots: PrioritySlots, priorities: list) -> list:
    order: list = []
    slots.acquire(0)
    threads = []
    for value in priorities:
        def run(value=value):
            with slots.slot(value):
                order.append(value)
        thread = threading.Thread(target=run)
        thread.start()
        threads.append(thread)
        time.sleep(0.05)
    deadline = time.time() + 2
    while slots.waiting < len(priorities) and time.time() < deadline:
        time.sleep(0.01)
    slots.release()
    for thread in threads:
        thread.join(2)
    return order


def test_critical_reports_leave_the_queue_first():
    slots = PrioritySlots(1)
    low, high, critical = report_priority(30), report_priority(65), report_priority(92)
    assert _queue_behind(slots, [low, high, critical]) == [critical, high, low]


def test_the_desk_question_goes_ahead_of_queued_reports():
    slots = PrioritySlots(1)
    assert _queue_behind(slots, [report_priority(95), DESK])[0] == DESK


def test_priority_follows_the_calling_thread():
    slots = PrioritySlots(1)
    with ai_priority(report_priority(80)):
        slots.acquire()
    assert slots.served[-1] == -80.0
    slots.release()


def _live(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    monkeypatch.setattr(settings, "GEMINI_ENABLED", True)
    monkeypatch.setattr(settings, "AI_MODE", "auto")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key-not-a-secret")
    monkeypatch.setattr(settings, "GEMINI_TIMEOUT_S", 1.0)
    monkeypatch.setattr("app.llm.client.CACHE_DIR", tmp_path)
    monkeypatch.setattr(llm_client.guard, "gap", 0.0)
    monkeypatch.setattr(llm_client.guard, "failures", 0)


class _Models:
    def __init__(self, reply: str):
        self.reply = reply

    def generate_content(self, **kwargs):
        class R:
            text = self.reply
            usage_metadata = None
        return R()


def test_a_full_gate_waits_instead_of_falling_back(monkeypatch, tmp_path):
    _live(monkeypatch, tmp_path)
    monkeypatch.setattr(llm_client, "_make_genai_client", lambda t: type("C", (), {"models": _Models("{\"ok\": true}")})())
    size = llm_client.guard.slots.size
    llm_client.guard.slots.resize(1)
    llm_client.guard.slots.acquire(0)
    out = {}

    def call():
        out["text"] = llm_client.generate_content("system", f"ZXQUEUE{uuid.uuid4().hex[:8]} a boat please")
        out["provider"] = llm_client.last_ai.provider

    worker = threading.Thread(target=call)
    try:
        worker.start()
        # Held longer than the 1 s call timeout: the old semaphore gave up here and used rules.
        time.sleep(1.5)
        assert "text" not in out
    finally:
        llm_client.guard.slots.release()
        worker.join(3)
        llm_client.guard.slots.resize(size)
    assert out["provider"] == "gemini"
    assert out["text"] == "{\"ok\": true}"


def test_ask_the_desk_is_one_call_and_cached_by_question(monkeypatch, tmp_path):
    _live(monkeypatch, tmp_path)
    calls = []

    def fake(question, timeout_s):
        calls.append(question)
        return {"types": ["rescue"], "reason": "Searched rescue cases."}, 12

    question = f"Which rescue cases are waiting {uuid.uuid4().hex[:6]}?"
    first = desk_query.ask(question, [], call=fake)
    assert len(calls) == 1
    assert first["ai"]["provider"] == "gemini"
    again, meta = desk_query.gemini_filters(question)
    assert len(calls) == 1
    assert meta["provider"] == "cache"
    assert again["types"] == ["rescue"]


def test_ranked_team_candidates_are_not_staff_assignments():
    assert client.post("/api/demo/reset", headers=AUTH).status_code == 200
    listed = client.get("/api/requests", headers=AUTH).json()
    for row in listed[:2]:
        client.get(f"/api/requests/{row['id']}/matches", headers=AUTH)
    body = client.get("/api/assist/proposals", headers=AUTH).json()
    assert body["proposals"] == []
    planned = client.post("/api/assist/plan", headers=AUTH).json()
    assert all(row["expires_at"] for row in planned["proposals"])
    for row in planned["proposals"]:
        client.post(f"/api/matches/{row['match_id']}/reject", headers=AUTH, json={"reason": "test release"})
    assert client.post("/api/demo/full", headers=AUTH).status_code == 200
