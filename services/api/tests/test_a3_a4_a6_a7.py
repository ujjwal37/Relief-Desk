"""Tests for frozen demo sections A3 (input gate), A4 (receipt), A6 (no invented fields), and A7 (photo with same send)."""
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.llm.client import llm_client
from app.main import app
from app.models.schemas import ExtractedRequest, HazardType, IncidentType, PeopleInfo, VulnerableFlags
from app.tools.input_gate import evaluate_input_gate
from app.agents.no_team import calculate_no_team
from app.models.firestore_models import StoredRequest, StoredResource, ResourceKind

client = TestClient(app)
AUTH = {"Authorization": "Bearer demo-coordinator-token"}


@pytest.fixture
def mock_gemini_client(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    monkeypatch.setattr(settings, "GEMINI_ENABLED", True)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key-mocked")
    monkeypatch.setattr("app.llm.client.CACHE_DIR", tmp_path)
    llm_client._memory_cache.clear()
    llm_client._memory_source.clear()
    yield
    llm_client._memory_cache.clear()
    llm_client._memory_source.clear()


def test_messy_inputs_gate_fallback():
    """All 18 messy inputs from messy_inputs.json must produce expected gate outcomes on fallback."""
    json_path = Path(__file__).parent / "data" / "messy_inputs.json"
    assert json_path.exists(), f"Missing {json_path}"
    with open(json_path, encoding="utf-8") as f:
        cases = json.load(f)

    for case in cases:
        name = case["name"]
        text = case["input"]
        expected = case["expected"]
        lang = case.get("lang", "en")
        outcome, reply = evaluate_input_gate(text, lang=lang)
        assert outcome == expected, f"Case '{name}' ('{text}') expected {expected}, got {outcome}"
        if expected != "report":
            assert reply is not None, f"Expected gate reply for '{name}'"


def test_a3_gate_api_greeting_and_gibberish():
    """Greetings and gibberish must return is_case=False and not create cases."""
    # 1. Greeting
    res = client.post("/api/reports", json={"text": "hi", "lang": "en"})
    assert res.status_code == 200
    data = res.json()
    assert data["is_case"] is False
    assert data["gate_outcome"] == "greeting"
    assert "Tell me what's happening" in data["gate_reply"]

    # 2. Gibberish
    res = client.post("/api/reports", json={"text": "asdfghjk qwerty zzz", "lang": "en"})
    assert res.status_code == 200
    data = res.json()
    assert data["is_case"] is False
    assert data["gate_outcome"] == "gibberish"
    assert "couldn't understand" in data["gate_reply"]

    # 3. Life-threat bypasses gate even if short
    res = client.post("/api/reports", json={"text": "not breathing", "lang": "en"})
    assert res.status_code == 200
    data = res.json()
    assert data["is_case"] is True
    assert data["report_id"] is not None


def test_a4_receipt_in_reporter_language():
    """A report creates a localized receipt from extracted facts."""
    res = client.post(
        "/api/reports",
        json={
            "text": "3 people trapped near Kainakary church, water rising rapidly",
            "lang": "en",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["is_case"] is True
    report_id = data["report_id"]
    receipt = data.get("receipt")
    assert receipt is not None
    assert "Received RD-" in receipt
    assert "3 people" in receipt

    status_token = data.get("status_token")
    # Status endpoint returns the receipt and place_stated
    status_res = client.get(f"/api/reports/{report_id}/status", params={"token": status_token})
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["receipt"] == receipt
    assert "place_stated" in status_data


def test_a4_update_report_location_same_case():
    """Share location updates coordinates on the SAME case."""
    res = client.post(
        "/api/reports",
        json={"text": "Four people stuck, water rising", "lang": "en"},
    )
    report_data = res.json()
    report_id = report_data["report_id"]
    status_token = report_data.get("status_token")

    loc_res = client.post(
        f"/api/reports/{report_id}/location",
        json={"lat": 9.501, "lng": 76.432, "accuracy": 15, "source": "gps", "token": status_token},
    )
    assert loc_res.status_code == 200
    assert loc_res.json()["ok"] is True
    assert loc_res.json()["report_id"] == report_id

    # Verify status now reflects stated location
    status_res = client.get(f"/api/reports/{report_id}/status", params={"token": status_token})
    assert status_res.status_code == 200
    assert status_res.json()["place_stated"] is True


def test_a6_no_invented_fields_quoted_span():
    """RD-9914 fix: server rejects client structured facts that do not appear in raw text."""
    res = client.post(
        "/api/reports",
        json={
            "text": "waiting beside water",
            "raw_text": "waiting beside water",
            "structured": {
                "incident_type": "rescue",
                "people_count": 9,  # Unquoted, not in text!
                "place_text": "Alappuzha market",  # Unquoted, not in text!
            },
            "lang": "en",
        },
    )
    assert res.status_code == 200
    data = res.json()
    # Receipt must say "Place: not stated" because "Alappuzha market" was not quoted in text!
    receipt = data.get("receipt", "")
    assert "Place: not stated" in receipt or "Alappuzha market" not in receipt


def test_a6_no_team_no_tilde_question_min():
    """When location is missing, calculate_no_team must not return reserve/road/wider (~? min)."""
    req = StoredRequest(
        id="req_test_nolocation",
        raw_text="Help needed",
        lat=None,
        lng=None,
        urgency_score=75,
    )
    resources = [
        StoredResource(
            id="res_boat_1",
            name="Boat Alpha",
            kind=ResourceKind.BOAT,
            status="busy",
            ward_id="ward_1",
            lat=9.50,
            lng=76.43,
            capacity_total=10,
            capacity_remaining=0,
            busy_until_min=20,
        )
    ]
    no_team = calculate_no_team(req, resources, boats_free=False, medical_free=True)
    assert no_team.options.reserve is None
    assert no_team.options.road is None
    assert no_team.options.wider is None
    assert no_team.options.escalate is not None


def test_a7_photo_with_same_send(mock_gemini_client):
    """Photo sent with the same report is preserved and creates a case."""
    dummy_photo = "data:image/jpeg;base64,/9j/4AAQSkZJRg=="
    res = client.post(
        "/api/reports",
        json={
            "text": "Water rising rapidly, trapped on roof",
            "photo_base64": dummy_photo,
            "lang": "en",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["is_case"] is True
    report_id = data["report_id"]

    # Verify status
    status_res = client.get(f"/api/reports/{report_id}/status", params={"token": data.get("status_token")})
    assert status_res.status_code == 200


def test_a7_photo_gate_unrelated_photo_no_case(monkeypatch):
    """An unrelated photo (selfie/meme) with no text gets 'couldn't understand' and NO case."""
    from app.agents.intake import intake_agent, ReportAnalysis
    from app.models.schemas import AiCall

    unrelated = ReportAnalysis(
        type=IncidentType.OTHER,
        hazard=HazardType.NONE,
        people=PeopleInfo(count=None),
        notes="A portrait photo of a person smiling indoors.",
    )
    monkeypatch.setattr(intake_agent, "parse_media_report", lambda *args, **kwargs: unrelated)
    monkeypatch.setattr(llm_client, "last_ai", AiCall(provider="gemini", model="gemini-2.0-flash"))

    dummy_photo = "data:image/jpeg;base64,/9j/4AAQSkZJRg=="
    res = client.post(
        "/api/reports",
        json={"text": "", "photo_base64": dummy_photo, "lang": "en"},
    )
    assert res.status_code == 200
    data = res.json()
    status_res = client.get(f"/api/reports/{data['report_id']}/status", params={"token": data.get("status_token")})
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["is_case"] is False
    assert status_data["gate_outcome"] == "gibberish"
    assert "couldn't understand" in status_data["gate_reply"]


def test_a7_photo_gate_fallback_honest_needs_review(monkeypatch):
    """When the model is unavailable (fallback), a photo-only report creates a case marked needs_human_review, never guessed rescue."""
    from app.agents.intake import intake_agent
    from app.models.schemas import AiCall

    def raise_err(*args, **kwargs):
        raise RuntimeError("Model unavailable")

    monkeypatch.setattr(intake_agent, "parse_media_report", raise_err)
    monkeypatch.setattr(llm_client, "last_ai", AiCall(provider="fallback"))

    dummy_photo = "data:image/jpeg;base64,/9j/4AAQSkZJRg=="
    res = client.post(
        "/api/reports",
        json={"text": "", "photo_base64": dummy_photo, "lang": "en"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["is_case"] is True
    assert "needs_human_review" in data["flags"]

    from app.tools.storage import storage_service
    req = storage_service.get_request(data["request_id"])
    assert req is not None
    assert req.type == IncidentType.OTHER
    assert req.hazard in (HazardType.NONE, HazardType.UNKNOWN)


def test_manglish_gate_and_receipt():
    """Latin-script Manglish input gets Manglish Latin reply/receipt, not Malayalam script."""
    res = client.post(
        "/api/reports",
        json={
            "text": "Champakulam church-nte aduthu vellam koodi, aalukal ottappettu, 4 per undu, ammachi nadakkan pattilla",
            "lang": "manglish",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["is_case"] is True
    receipt = data.get("receipt", "")
    assert "Labhichu RD-" in receipt
    assert "Manassilayathu:" in receipt
    # Ensure no Malayalam script characters
    assert not any("\u0D00" <= c <= "\u0D7F" for c in receipt)


def test_photo_endpoint_coordinator_auth():
    """Photo is served from GET /api/requests/{id}/photo with coordinator auth."""
    dummy_photo = "data:image/jpeg;base64,/9j/4AAQSkZJRg=="
    res = client.post(
        "/api/reports",
        json={
            "text": "Water rising rapidly, trapped on roof",
            "photo_base64": dummy_photo,
            "lang": "en",
        },
    )
    assert res.status_code == 200
    req_id = res.json()["request_id"]

    # Requests list does NOT include photo_base64
    list_res = client.get("/api/requests", headers=AUTH)
    assert list_res.status_code == 200
    target = next((r for r in list_res.json() if r["id"] == req_id), None)
    assert target is not None
    assert target["photo_base64"] is None
    assert target["has_photo"] is True

    # Photo endpoint works with auth
    photo_res = client.get(f"/api/requests/{req_id}/photo", headers=AUTH)
    assert photo_res.status_code == 200
    assert photo_res.headers["content-type"] == "image/jpeg"
    assert len(photo_res.content) > 0

    # Photo endpoint rejects unauthenticated request
    no_auth_res = client.get(f"/api/requests/{req_id}/photo")
    assert no_auth_res.status_code == 401

