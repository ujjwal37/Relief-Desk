"""Spam intake is flagged and kept out of the Needs help now band."""
import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.models.firestore_models import StoredRequest
from app.models.schemas import HazardType, IncidentType, VulnerableFlags
from app.tools.scoring import scoring_engine
from app.tools.storage import storage_service

client = TestClient(app)
SPAM = "FREE MONEY click bit.ly win iphone send OTP"
NEEDS_HELP = 60


def test_spam_sample_is_flagged_and_stays_out_of_needs_help():
    token = uuid.uuid4().hex[:8]
    response = client.post(
        "/api/reports",
        json={
            "text": SPAM,
            "lang": "en",
            "channel": "text",
            "idempotency_key": f"hoax-{token}",
            "location_pin": {"lat": 9.45, "lng": 76.39},
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "hoax" in body["flags"]
    stored = storage_service.get_request(body["request_id"])
    assert stored is not None
    assert "hoax" in stored.flags
    assert stored.urgency_score < NEEDS_HELP
    assert storage_service.get_report(body["report_id"]) is not None


def test_hoax_flag_caps_a_score_that_would_otherwise_need_help():
    urgent = StoredRequest(
        id="req_would_be_critical",
        type=IncidentType.RESCUE,
        people_count=8,
        vulnerable=VulnerableFlags(child=True, elderly=True),
        hazard=HazardType.WATER_RISING,
    )
    open_score = scoring_engine.compute_urgency(urgent).score
    urgent.flags = ["hoax"]
    capped = scoring_engine.compute_urgency(urgent)
    assert open_score >= NEEDS_HELP
    assert capped.score <= 40
    assert capped.score < NEEDS_HELP
    assert "hoax" in capped.reason or "spam" in capped.reason


def test_seeded_hoax_is_caught_by_rules_with_gemini_off(monkeypatch):
    """The demo-pack hoax is flagged by the rule phrases alone, so a Gemini miss or outage cannot let it through."""
    from app.config import settings
    from app.tools.demo_seed import build_demo_reports
    from app.tools.trust import hoax_reason_for

    monkeypatch.setattr(settings, "GEMINI_ENABLED", False, raising=False)
    seeded = next(row["text"] for row in build_demo_reports() if row.get("kind") == "hoax")
    assert hoax_reason_for(seeded)
    token = uuid.uuid4().hex[:8]
    response = client.post(
        "/api/reports",
        json={"text": seeded, "lang": "en", "channel": "text", "idempotency_key": f"hoax-seed-{token}",
              "location_pin": {"lat": 9.45, "lng": 76.39}},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "hoax" in body["flags"]
    stored = storage_service.get_request(body["request_id"])
    assert stored is not None and stored.urgency_score < NEEDS_HELP
