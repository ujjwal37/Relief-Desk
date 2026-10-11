from fastapi.testclient import TestClient

from app.main import app
from app.tools.storage import storage_service

client = TestClient(app)

HERO = "Gandhi school ke paas 5 log chat par hain, paani badh raha hai, 2 bache hain"


def test_chat_turn_does_not_create_a_request():
    before = {req.id for req in storage_service.list_requests()}
    resp = client.post(
        "/api/intake/chat",
        json={"session_id": "confirm_no_submit", "message": HERO, "scenario_id": "flood", "language": "hinglish"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["confirmation_card"]["ready_to_submit"] is True
    after = {req.id for req in storage_service.list_requests()}
    assert after == before


def test_submit_persists_only_after_explicit_confirm_and_keeps_edits():
    before = {req.id for req in storage_service.list_requests()}
    resp = client.post(
        "/api/reports",
        json={
            "text": "5 people needing rescue at Ward 7",
            "lang": "en",
            "scenario_id": "flood",
            "location_pin": {"lat": 26.852, "lng": 80.925},
            "structured": {
                "incident_type": "rescue",
                "place_text": "Ward 7 · Gandhi School",
                "people_count": 8,
                "vulnerable": {"child": True, "elderly": True, "disabled": False, "pregnant": False, "medical_need": False},
                "hazard": "water_rising",
                "summary": "8 people needing rescue at Ward 7 · Gandhi School",
            },
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    created = [req for req in storage_service.list_requests() if req.id not in before]
    assert len(created) == 1
    stored = created[0]
    assert stored.id == body["request_id"]
    assert stored.people_count == 8
    assert stored.place_text == "Ward 7 · Gandhi School"
    assert stored.vulnerable.child is True
    assert stored.vulnerable.elderly is True
    assert stored.type.value == "rescue"
    assert body["status_token"]
