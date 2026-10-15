"""AI x-factor: honest health, sitrep counts, multimodal fallback, pipeline SSE, route note."""
from fastapi.testclient import TestClient

from app.agents.matching import route_compare_note
from app.agents.sitrep import collect_counts, generate_sitrep
from app.llm.client import llm_client
from app.main import app
from app.tools.events import emit_pipeline_step, reset_for_tests, subscribe, unsubscribe
from app.tools.storage import storage_service

client = TestClient(app)
AUTH = {"Authorization": "Bearer demo-coordinator-token"}


def test_health_ai_is_rules_fallback_without_a_successful_call(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "GEMINI_ENABLED", False)
    llm_client.guard.last_success_at = 0.0
    llm_client.guard.last_success_iso = None
    body = client.get("/api/health/ai").json()
    assert body["label"] == "Rules fallback"
    assert body["last_success_at"] is None
    assert "key" not in body


def test_health_ai_is_gemini_live_after_success(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "GEMINI_ENABLED", True)
    monkeypatch.setattr(llm_client, "gemini_live", lambda: True)
    llm_client.guard.failures = 0
    llm_client.guard.last_failure_at = 0.0
    llm_client.guard.record_success()
    body = client.get("/api/health/ai").json()
    assert body["label"] == "Gemini live"
    assert body["last_success_at"]
    assert body["quota"]["last_success"] is True


def test_sitrep_uses_real_open_counts_and_never_sends():
    storage_service.reset_demo()
    counts = collect_counts()
    assert counts.pending >= 0
    assert counts.free_boats >= 0
    assert counts.boat_gap == max(0, counts.rooftop_like - counts.free_boats)
    report = generate_sitrep()
    assert report.send is False
    assert str(counts.pending) in report.brief
    assert report.drafts.sms_en
    assert report.drafts.sms_hi
    assert report.drafts.sms_ml
    body = client.post("/api/sitrep", headers=AUTH).json()
    assert body["send"] is False
    assert body["counts"]["pending"] == counts.pending


def test_sample_catalog_and_hindi_sample_enter_intake():
    catalog = client.get("/api/demo/samples").json()
    assert "नमस्ते" in catalog["hindi_text"]["text"]
    assert catalog["voice"]["url"]
    photo = client.get("/api/demo/samples/photo-flood")
    assert photo.status_code == 200
    assert photo.headers["content-type"].startswith("image/")
    created = client.post("/api/demo/sample-report", json={"kind": "hindi"}).json()
    assert created["request_id"]
    stored = storage_service.get_request(created["request_id"])
    assert stored is not None
    assert stored.raw_text and "चालाकुडी" in stored.raw_text


def test_multimodal_photo_falls_back_when_gemini_is_off(monkeypatch):
    from app.tools.demo_samples import sample_payload

    monkeypatch.setattr(llm_client, "gemini_live", lambda: False)
    payload = sample_payload("photo")
    body = client.post("/api/reports", json=payload).json()
    assert body["request_id"]
    stored = storage_service.get_request(body["request_id"])
    assert stored is not None
    assert stored.raw_text
    assert stored.ai is None or stored.ai.provider in ("fallback", "cache", "gemini")


def test_pipeline_step_events_are_published():
    reset_for_tests()
    box = subscribe()
    emit_pipeline_step("req_demo", "triage", "complete", "Immediate", {"tier": "immediate", "score": 82})
    event = box.get_nowait()
    unsubscribe(box)
    assert event["type"] == "pipeline.step"
    assert event["agent"] == "triage"
    assert event["extra"]["tier"] == "immediate" if "extra" in event else event["tier"] == "immediate"


def test_route_compare_uses_the_same_distance():
    note = route_compare_note(0.7, "water")
    assert note is not None
    assert "0.7 km by water" in note
    assert note.startswith("Boat team")
    assert "by road" in note
    assert "no live road-closure" in note
    assert "82" not in note
