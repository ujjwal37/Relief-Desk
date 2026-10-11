"""Intake keeps a structured reading: type, place, ward, people, hazard, language, hoax."""
import uuid

from fastapi.testclient import TestClient

from app.agents.intake import intake_agent
from app.main import app
from app.models.schemas import IncidentType
from app.tools.storage import storage_service

client = TestClient(app)
SPAM = "FREE MONEY click bit.ly win iphone send OTP"


def test_hinglish_and_tamil_extract_the_structured_fields():
    hinglish = intake_agent.parse_report(
        "Champakulam School ke paas 4 log chhat par hain, boat bhejo",
        language_hint="hinglish",
    )
    assert hinglish.type == IncidentType.RESCUE
    assert hinglish.people.count == 4
    assert hinglish.ward_id == "ward_2"
    assert hinglish.vulnerable.child is False
    assert hinglish.hazard.value == "stranded"
    assert hinglish.language.value in ("hinglish", "en")
    assert hinglish.confidence.type > 0
    assert hinglish.hoax_score == 0
    assert "Champakulam" in (hinglish.original_text or "")

    tamil = intake_agent.parse_report("வராப்புழாவில் 5 பேர் சிக்கியுள்ளனர்", language_hint="ta")
    assert tamil.people.count == 5
    assert tamil.language.value == "ta"
    assert tamil.original_text.startswith("வராப்புழாவில்")
    assert tamil.hoax_score == 0


def test_spam_sample_is_scored_and_kept_out_of_needs_help():
    parsed = intake_agent.parse_report(SPAM, language_hint="en")
    assert parsed.hoax_score >= 0.9
    assert parsed.original_text == SPAM
    token = uuid.uuid4().hex[:8]
    created = client.post(
        "/api/reports",
        json={
            "text": f"{SPAM} {token}",
            "lang": "en",
            "channel": "text",
            "location_pin": {"lat": 9.45, "lng": 76.39},
            "idempotency_key": f"spam-{token}",
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert "hoax" in body["flags"]
    assert body["urgency_score"] < 75
    stored = storage_service.get_request(body["request_id"])
    assert stored is not None
    # A second copy of the same spam can fold into the first card.
    open_id = stored.merged_into or stored.id
    listed = client.get("/api/requests", headers={"Authorization": "Bearer demo-coordinator-token"})
    card = next(row for row in listed.json() if row["id"] == open_id)
    assert "FREE MONEY" in (card.get("raw_text") or "")
    assert card["urgency_score"] < 75
    report = storage_service.get_report(body["report_id"])
    assert report is not None
    assert report.raw_text.startswith(SPAM)
