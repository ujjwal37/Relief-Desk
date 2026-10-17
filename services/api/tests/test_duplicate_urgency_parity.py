"""The same situation in different words or languages is planned at one urgency (judge r6, item 1)."""
from fastapi.testclient import TestClient

from app.agents import pipeline
from app.main import app
from app.tools.storage import storage_service

client = TestClient(app)
AUTH = {"Authorization": "Bearer demo-coordinator-token"}
PIN = {"lat": 9.470, "lng": 76.392}


def _send(text: str, lang: str) -> str:
    res = client.post("/api/reports", json={"text": text, "lang": lang, "location_pin": PIN})
    assert res.status_code in (200, 201), res.text
    pipeline.wait_for_idle(20)
    return res.json()["request_id"]


def test_manglish_and_english_reports_of_one_situation_score_within_5():
    client.post("/api/demo/full", headers=AUTH)
    first = _send("Kainakary boat jetty aduthu 3 per kudungi, vellam nenju vare, boat venam", "en")
    second = _send("4 people stuck near Kainakary boat jetty, water is chest-deep, need a boat", "en")
    a, b = storage_service.get_request(first), storage_service.get_request(second)
    assert b.possible_duplicate is not None and b.possible_duplicate.target_id == first
    assert abs(a.urgency_score - b.urgency_score) <= 5, (a.urgency_score, b.urgency_score)
    assert "3 vs 4 people → plan for 4" in (b.count_note or "")
    assert "RD-" in (b.count_note or "")
