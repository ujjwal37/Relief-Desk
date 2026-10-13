"""POST returns the report id before a slow model finishes."""
import queue
import threading
import time
import uuid

from fastapi.testclient import TestClient

from app.agents.intake import extract_with_rules
from app.agents.pipeline import _start_thread, wait_for_idle
from app.main import app
from app.tools.events import subscribe, unsubscribe
from app.tools.storage import storage_service
from app.tools.translation import TranslationResult
from app.tools.wait_tips import RESCUE

client = TestClient(app)


def test_submit_returns_before_a_slow_model(monkeypatch):
    marks = []
    lock = threading.Lock()

    def slow_parse(raw_text, language_hint=None):
        with lock:
            marks.append(("parse", time.perf_counter()))
        time.sleep(0.6)
        return extract_with_rules(raw_text)

    def slow_translate(text, allow_model=True):
        with lock:
            marks.append(("translate", allow_model))
        return TranslationResult(
            text_en=text,
            text_hi=text,
            translations={"en": text, "hi": text},
            detected_language="en",
            confidence=0.95,
            is_low_confidence=False,
        )

    monkeypatch.setattr("app.agents.pipeline._spawn", _start_thread)
    monkeypatch.setattr("app.api.reports.intake_agent.parse_report", slow_parse)
    monkeypatch.setattr("app.api.reports.translation_service.translate_report", slow_translate)

    box = subscribe()
    token = uuid.uuid4().hex[:8]
    place = f"Slowjetty{token}"
    try:
        started = time.perf_counter()
        created = client.post(
            "/api/reports",
            json={
                "text": f"4 people stranded near {place}, send a boat",
                "lang": "en",
                "channel": "text",
                "location_pin": {"lat": 9.416, "lng": 76.411},
                "idempotency_key": f"slow-{token}",
                "structured": {
                    "incident_type": "rescue",
                    "place_text": place,
                    "people_count": 4,
                    "hazard": "water_rising",
                },
            },
        )
        elapsed = time.perf_counter() - started
        assert created.status_code == 200, created.text
        assert elapsed < 1.0, elapsed
        body = created.json()
        assert body["report_id"]
        assert body["status_token"]
        stored = storage_service.get_request(body["request_id"])
        assert stored is not None
        assert stored.analysis_status == "analysing"
        assert stored.type.value == "rescue"
        assert stored.place_text == place
        status_res = client.get(f"/api/reports/{body['report_id']}/status?token={body['status_token']}")
        assert status_res.status_code == 200
        status_body = status_res.json()
        assert status_body["while_you_wait_tips"] == list(RESCUE)
        assert status_body["analysis_status"] == "analysing"

        assert wait_for_idle(3.0)
        done = storage_service.get_request(body["request_id"])
        assert done is not None
        assert done.analysis_status == "complete"
        kinds = []
        while True:
            try:
                event = box.get_nowait()
            except queue.Empty:
                break
            ids = {str(item) for item in (event.get("request_ids") or [])}
            if event.get("request_id"):
                ids.add(str(event["request_id"]))
            if body["request_id"] in ids:
                kinds.append(event["type"])
        assert "case.created" in kinds
        assert "case.updated" in kinds or "case.merged" in kinds
        # One model call per report. The translation rides on it and never calls a model itself.
        assert [name for name, _ in marks].count("parse") == 1
        assert all(value is False for name, value in marks if name == "translate")
    finally:
        unsubscribe(box)
        wait_for_idle(3.0)
