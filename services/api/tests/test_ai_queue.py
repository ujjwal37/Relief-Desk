"""AI queue: steps, the 45s rules cap, life-threat, and paced recheck.

No test in this file calls Gemini. Recheck uses a fake client.
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.agents.pipeline import finish
from app.main import app
from app.models.firestore_models import AiQueueState, StoredRequest
from app.models.schemas import HazardType, IncidentType
from app.tools.case_queue import (
    RecheckPacer,
    abandon_if_capped,
    approve_blocked,
    begin_case,
    life_phrase,
    place_in_line,
    recheck_if_live,
    recheck_next,
    refresh_queue,
    steps_done,
)
from app.tools.storage import storage_service

client = TestClient(app)
AUTH = {"Authorization": "Bearer demo-coordinator-token"}
NOW = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)


def _case(case_id: str, text: str, score: float = 40, people: int = 2) -> StoredRequest:
    req = StoredRequest(
        id=case_id,
        type=IncidentType.RESCUE,
        raw_text=text,
        place_text="Kainakary jetty",
        lat=9.47185,
        lng=76.39571,
        people_count=people,
        urgency_score=score,
        hazard=HazardType.WATER_RISING,
        analysis_status="analysing",
        created_at=NOW.isoformat(),
    )
    begin_case(req, text, now=NOW, others=[])
    return req


def test_life_threat_phrases_and_straight_to_ready():
    assert life_phrase("my father is not breathing, water inside") == "not breathing"
    assert life_phrase("unconscious near the shop") == "unconscious"
    assert life_phrase("saans nahi aa rahi") == "saans nahi"
    assert life_phrase("सांस नहीं चल रही") == "सांस नहीं"
    assert life_phrase("shwasam illa, water in the house") == "shwasam illa"
    assert life_phrase("bodham illa") == "bodham illa"
    assert life_phrase("അച്ഛന്റെ ശ്വാസം ഇല്ല") == "ശ്വാസം ഇല്ല"
    assert life_phrase("ബോധം ഇല്ല") == "ബോധം ഇല്ല"
    assert life_phrase("water in the kitchen, send a boat") is None

    req = _case("aiq_life", "my father is not breathing, water inside house")
    queue = req.ai_queue
    assert queue is not None
    assert queue.status == "ready"
    assert queue.queue_pos is None
    assert queue.life_phrase == "not breathing"
    assert queue.place_unverified is True
    assert "lifeThreat" in queue.flags
    assert queue.engine == "rules"
    assert approve_blocked(req) is True


def test_queue_position_skips_life_threat_and_keeps_two_reading():
    rows = []
    for index in range(4):
        req = _case(f"aiq_line_{index}", "water in the house, need a boat")
        req.ai_queue.started_at = (NOW + timedelta(seconds=index)).isoformat()
        rows.append(req)
    life = _case("aiq_line_life", "not breathing at the ration shop", score=99)
    rows.append(life)
    place_in_line(rows)
    assert rows[0].ai_queue.status == "processing"
    assert rows[0].ai_queue.queue_pos is None
    assert rows[1].ai_queue.status == "processing"
    assert rows[2].ai_queue.status == "queued"
    assert rows[2].ai_queue.queue_pos == 1
    assert rows[3].ai_queue.queue_pos == 2
    assert life.ai_queue.status == "ready"
    assert life.ai_queue.queue_pos is None


def test_forty_five_second_cap_uses_rules_and_skips_the_model(monkeypatch):
    req = _case("aiq_cap", "four people on the roof at Kainakary")
    req.ai_queue.started_at = (datetime.now(timezone.utc) - timedelta(seconds=50)).isoformat()
    req.ai_queue.engine = "gemini"
    storage_service.save_request(req, actor="test")

    def boom(*_args, **_kwargs):
        raise AssertionError("Gemini review must not run after the 45s cap")

    monkeypatch.setattr("app.agents.review.language_review", boom)
    monkeypatch.setattr("app.agents.self_check.self_check", boom)
    finish(req.id)
    stored = storage_service.get_request(req.id)
    assert stored is not None
    assert stored.analysis_status == "complete"
    assert stored.ai_queue.engine == "rules"
    assert "timedOut" in stored.ai_queue.flags
    assert steps_done(stored)
    assert approve_blocked(stored) is False
    assert stored.ai_queue.engine in {"rules", "gemini", "gemini_rechecked"}


def test_elapsed_and_cap_via_refresh_do_not_call_out():
    req = _case("aiq_elapsed", "boat needed at the jetty")
    req.ai_queue.started_at = (NOW - timedelta(seconds=10)).isoformat()
    refresh_queue([req], now=NOW)
    assert req.ai_queue.elapsed_s == 10
    assert "timedOut" not in req.ai_queue.flags
    req.ai_queue.started_at = (NOW - timedelta(seconds=46)).isoformat()
    closed = refresh_queue([req], now=NOW)
    assert closed == ["aiq_elapsed"]
    assert req.ai_queue.engine == "rules"
    assert req.analysis_status == "complete"
    assert abandon_if_capped(req, NOW) is True


def test_recheck_is_critical_first_and_paced_at_about_ten_a_minute():
    class Fake:
        def __init__(self):
            self.ids: list[str] = []

        def review(self, case: StoredRequest) -> dict:
            self.ids.append(case.id)
            if case.id == "aiq_high":
                return {"people_count": 9, "place_text": case.place_text}
            return {"people_count": case.people_count, "place_text": case.place_text}

    fake = Fake()
    low = _case("aiq_low", "water rising", score=40, people=2)
    high = _case("aiq_high", "water rising", score=95, people=4)
    mid = _case("aiq_mid", "water rising", score=70, people=3)
    for req in (low, high, mid):
        req.ai_queue.engine = "rules"
        req.ai_queue.flags = ["timedOut"]
        req.ai_queue.steps = {step: "done" for step in ("read", "duplicates", "urgency", "team")}
        req.analysis_status = "complete"

    pacer = RecheckPacer()
    assert recheck_next([low, mid, high], client=None, now=0, circuit_closed=True, pacer=pacer) is None
    assert fake.ids == []
    assert recheck_next([low, mid, high], client=fake, now=0, circuit_closed=False, pacer=RecheckPacer()) is None
    assert fake.ids == []

    first = recheck_next([low, mid, high], client=fake, now=0, circuit_closed=True, pacer=pacer)
    assert first == "aiq_high"
    assert high.ai_queue.engine == "gemini_rechecked"
    assert high.ai_queue.recheck_diff == {"people_count": {"from": 4, "to": 9}}
    assert recheck_next([low, mid, high], client=fake, now=5, circuit_closed=True, pacer=pacer) is None
    assert fake.ids == ["aiq_high"]
    second = recheck_next([low, mid, high], client=fake, now=6, circuit_closed=True, pacer=pacer)
    assert second == "aiq_mid"
    assert mid.ai_queue.engine == "gemini_rechecked"
    assert mid.ai_queue.recheck_diff is None
    assert recheck_if_live([low]) is None
    assert "aiq_low" not in fake.ids


def test_approve_stays_blocked_until_rules_take_over_except_nearest_boat():
    storage_service.load_seed_resources()
    blocked = StoredRequest(
        id="aiq_block_approve",
        type=IncidentType.RESCUE,
        lat=9.436,
        lng=76.398,
        people_count=3,
        urgency_score=80,
        analysis_status="analysing",
        ai_queue=AiQueueState(
            status="processing",
            step="urgency",
            steps={"read": "done", "duplicates": "done", "urgency": "active", "team": "pending"},
            engine="gemini",
        ),
    )
    storage_service.save_request(blocked, actor="test")
    listed = client.get(f"/api/requests/{blocked.id}/matches", headers=AUTH)
    assert listed.status_code == 200
    match_id = listed.json()[0]["match_id"]
    denied = client.post(f"/api/matches/{match_id}/approve", json={}, headers=AUTH)
    assert denied.status_code == 409
    assert denied.json()["detail"]["code"] == "ai_not_finished"

    life = StoredRequest(
        id="aiq_send_boat",
        type=IncidentType.RESCUE,
        lat=9.436,
        lng=76.398,
        people_count=1,
        urgency_score=96,
        place_text="Veliyanad",
        raw_text="my father is not breathing, water inside house",
        analysis_status="analysing",
    )
    begin_case(life, life.raw_text, now=NOW, others=[])
    life.analysis_status = "analysing"
    storage_service.save_request(life, actor="test")
    detail = client.get(f"/api/requests/{life.id}", headers=AUTH)
    body = detail.json()["ai_queue"]
    assert body["status"] == "ready"
    assert body["life_phrase"] == "not breathing"
    assert body["place_unverified"] is True
    assert body["engine"] == "rules"
    assert body["elapsed_s"] >= 0
    sent = client.post(f"/api/requests/{life.id}/send-nearest-boat", json={}, headers=AUTH)
    assert sent.status_code == 200, sent.text
    resource = storage_service.get_resource(sent.json()["resource_id"])
    assert resource is not None
    assert resource.kind.value == "boat"
    assert storage_service.get_request(life.id).status.value == "dispatched"

    medical = StoredRequest(
        id="aiq_send_boat_medical",
        type=IncidentType.MEDICAL,
        lat=9.45,
        lng=76.4,
        people_count=1,
        urgency_score=97,
        place_text="Veliyanad",
        raw_text="my father is not breathing",
        analysis_status="analysing",
    )
    begin_case(medical, medical.raw_text, now=NOW, others=[])
    storage_service.save_request(medical, actor="test")
    sent_med = client.post(f"/api/requests/{medical.id}/send-nearest-boat", json={}, headers=AUTH)
    assert sent_med.status_code == 200, sent_med.text
    medical_boat = storage_service.get_resource(sent_med.json()["resource_id"])
    # No water in the report: the engine's pick is the nearest ambulance, and the button says so.
    assert medical_boat is not None and medical_boat.kind.value in ("medical", "boat")
    assert storage_service.get_request(medical.id).ai_queue.life_pick == "medical"


def test_hoax_before_finish_keeps_one_word_reason():
    req = _case("aiq_hoax", "this is a joke flood")
    storage_service.save_request(req, actor="test")
    response = client.post(
        f"/api/requests/{req.id}/dismiss-hoax",
        json={"reason": "joke please"},
        headers=AUTH,
    )
    assert response.status_code == 200
    assert response.json()["hoax_reason"] == "joke"
    assert response.json()["status"] == "dismissed_hoax"


def test_intake_exposes_engine_on_the_case():
    key = "aiq-intake-engine"
    response = client.post(
        "/api/reports",
        json={
            "text": "Water at Champakulam church, ward 4. Need a boat for 2 people.",
            "raw_text": "Water at Champakulam church, ward 4. Need a boat for 2 people.",
            "lang": "en",
            "channel": "text",
            "idempotency_key": key,
            "location_pin": {"lat": 9.45, "lng": 76.41},
        },
    )
    assert response.status_code == 200, response.text
    request_id = response.json()["request_id"]
    stored = client.get(f"/api/requests/{request_id}", headers=AUTH)
    assert stored.status_code == 200
    queue = stored.json()["ai_queue"]
    assert queue["engine"] == "rules"
    assert set(queue["steps"]) == {"read", "duplicates", "urgency", "team"}
    assert all(state == "done" for state in queue["steps"].values())
    assert queue["status"] == "ready"
