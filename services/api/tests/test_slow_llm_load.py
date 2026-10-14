"""Load: 5 reports in 10 s against a mocked local model that takes 12 s per call, one at a time.

Every submit answers under 1 s, merges show within 5 s, approval reaches the phone within 3 s,
critical cases get the model first, and nothing falls back because the queue was full.
"""
import asyncio
import json
import queue
import re
import threading
import time
import uuid

from fastapi.testclient import TestClient

from app.agents.intake import extract_with_rules
from app.agents.pipeline import _start_thread, wait_for_idle
from app.config import settings
from app.llm.client import llm_client
from app.main import app
from app.tools.events import subscribe, unsubscribe
from app.tools.storage import storage_service

client = TestClient(app)
AUTH = {"Authorization": "Bearer demo-coordinator-token"}
SLOW_S = 12.0
PIN_A = {"lat": 8.11, "lng": 77.21}
PIN_B = {"lat": 8.30, "lng": 77.40}
PIN_C = {"lat": 8.45, "lng": 77.55}


class _Reply:
    def __init__(self, text: str):
        self.text = text
        self.usage_metadata = None


class _SlowModels:
    """Answers like a local model: one call at a time, SLOW_S each, until the test releases it."""

    def __init__(self, release: threading.Event, started: list):
        self.release = release
        self.started = started
        self.busy = threading.Lock()

    def generate_content(self, model, contents, config):
        report = re.search(r"<report>\n(.*?)\n</report>", contents, re.DOTALL).group(1)
        with self.busy:
            self.started.append((time.perf_counter(), report))
            self.release.wait(SLOW_S)
        parsed = extract_with_rules(report).model_dump(mode="json")
        parsed.update(text_en=report, text_hi=report, translation_confidence=0.93)
        return _Reply(json.dumps(parsed, ensure_ascii=False))


class _SlowClient:
    def __init__(self, models):
        self.models = models


def _phone_stream(case_id: str, frames: list, stop: threading.Event) -> None:
    from app.api.events import _stream

    class Req:
        async def is_disconnected(self) -> bool:
            return stop.is_set()

    async def read() -> None:
        agen = _stream(Req(), case_id)
        try:
            async for chunk in agen:
                frames.append((time.perf_counter(), chunk))
                if stop.is_set():
                    break
        finally:
            await agen.aclose()

    asyncio.run(read())


def _post(text: str, pin: dict, key: str) -> tuple[dict, float]:
    started = time.perf_counter()
    res = client.post(
        "/api/reports",
        json={"text": text, "raw_text": text, "lang": "en", "channel": "text",
              "location_pin": pin, "idempotency_key": key, "source_id": key},
    )
    elapsed = time.perf_counter() - started
    assert res.status_code == 200, res.text
    return res.json(), elapsed


def _merged_into(request_id: str):
    req = storage_service.get_request(request_id)
    return req.merged_into if req else None


def _wait_for(check, timeout: float) -> float:
    started = time.perf_counter()
    while time.perf_counter() - started < timeout:
        if check():
            return time.perf_counter() - started
        time.sleep(0.05)
    raise AssertionError(f"not true within {timeout}s")


def test_five_reports_against_a_slow_local_model(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    monkeypatch.setattr(settings, "GEMINI_ENABLED", True)
    monkeypatch.setattr(settings, "AI_MODE", "auto")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key-not-a-secret")
    monkeypatch.setattr(settings, "GEMINI_TIMEOUT_S", 30.0)
    monkeypatch.setattr("app.llm.client.CACHE_DIR", tmp_path)
    monkeypatch.setattr("app.agents.pipeline._spawn", _start_thread)
    monkeypatch.setattr("app.api.events.HEARTBEAT_SECONDS", 0.5)
    monkeypatch.setattr("app.agents.dedupe.dedupe_agent.embedder", lambda texts: None)
    monkeypatch.setattr(llm_client.guard, "gap", 0.0)
    monkeypatch.setattr(llm_client.guard, "failures", 0)
    size_before = llm_client.guard.slots.size
    llm_client.guard.slots.resize(1)

    release = threading.Event()
    started_calls: list = []
    models = _SlowModels(release, started_calls)
    monkeypatch.setattr(llm_client, "_make_genai_client", lambda timeout_s: _SlowClient(models))

    token = f"Kestrel{uuid.uuid4().hex[:6]}"
    farm = f"Marigold{uuid.uuid4().hex[:6]}"
    clinic = f"Juniper{uuid.uuid4().hex[:6]}"
    plan = [
        (f"5 people stranded on the roof at {token} jetty, water rising, send a boat", PIN_A),
        (f"People stranded above the water at {token} jetty, send a rescue boat", PIN_A),
        (f"2 families need drinking water and ration at {farm} school", PIN_B),
        (f"Still stranded at {token} jetty, send a boat, people are on the roof", PIN_A),
        (f"Child bleeding and unconscious at {clinic} clinic, oxygen and a doctor needed now", PIN_C),
    ]

    bus = subscribe()
    stop = threading.Event()
    frames: list = []
    phone = None
    bodies = []
    try:
        t0 = time.perf_counter()
        for index, (text, pin) in enumerate(plan):
            at = t0 + index * 2.0
            time.sleep(max(0.0, at - time.perf_counter()))
            body, elapsed = _post(text, pin, f"load-{token}-{index}")
            assert elapsed < 1.0, (index, elapsed)
            bodies.append(body)
            if index == 0:
                phone = threading.Thread(target=_phone_stream, args=(body["request_id"], frames, stop), daemon=True)
                phone.start()
            if index in (1, 3):
                primary = bodies[0]["request_id"]
                shell = body["request_id"]
                took = _wait_for(lambda: _merged_into(shell) == primary, 5.0)
                assert took < 5.0
        assert time.perf_counter() - t0 < 10.0

        primary = storage_service.get_request(bodies[0]["request_id"])
        assert primary is not None and primary.merged_count == 3
        merged_events = []
        while True:
            try:
                event = bus.get_nowait()
            except queue.Empty:
                break
            if event["type"] == "case.merged" and primary.id in (event.get("request_ids") or []):
                merged_events.append(event)
        assert len(merged_events) >= 2

        waiting = storage_service.get_request(bodies[2]["request_id"])
        assert waiting is not None and waiting.analysis_status == "analysing"
        assert primary.analysis_status == "analysing"

        before_approve = len(frames)
        approve_at = time.perf_counter()
        matches = client.get(f"/api/requests/{primary.id}/matches", headers=AUTH)
        assert matches.status_code == 200 and matches.json()
        approved = client.post(f"/api/matches/{matches.json()[0]['match_id']}/approve", headers=AUTH, json={})
        assert approved.status_code == 200, approved.text
        status_url = f"/api/reports/{bodies[0]['report_id']}/status?token={bodies[0]['status_token']}"
        reached = _wait_for(lambda: client.get(status_url).json()["hero_title"] == "status.heroOnWay", 3.0)
        assert reached < 3.0
        pushed = _wait_for(
            lambda: any("dispatch.created" in chunk or "case.updated" in chunk for _, chunk in frames[before_approve:]),
            3.0,
        )
        assert time.perf_counter() - approve_at < 3.0, pushed

        # The first call frees its slot at about 12 s. The critical clinic case goes before the earlier food case.
        _wait_for(lambda: len(started_calls) >= 2, SLOW_S + 3.0)
        assert clinic in started_calls[1][1]
        assert len(started_calls) == 2
    finally:
        release.set()
        stop.set()
        unsubscribe(bus)
        assert wait_for_idle(15.0)
        if phone is not None:
            phone.join(3.0)
        llm_client.guard.slots.resize(size_before)

    reports = [report for _, report in started_calls]
    assert len(reports) == 3, reports
    assert not any("Still stranded" in text or "above the water" in text for text in reports)
    for body in (bodies[0], bodies[2], bodies[4]):
        done = storage_service.get_request(body["request_id"])
        assert done is not None
        assert done.analysis_status == "complete"
        assert done.ai is not None and done.ai.provider == "gemini", done.ai
        assert done.translations.get("en")
    assert storage_service.get_request(bodies[0]["request_id"]).status.value == "dispatched"
