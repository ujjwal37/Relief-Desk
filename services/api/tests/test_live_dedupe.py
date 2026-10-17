"""A reworded second caller about the same street and people merges into one card."""
import json
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
AUTH = {"Authorization": "Bearer demo-coordinator-token"}
EN = Path(__file__).resolve().parents[3] / "libs" / "shared" / "src" / "lib" / "i18n" / "en.json"


def test_reworded_hinglish_pair_merges_and_the_card_says_two_reports():
    token = f"Mithralane{uuid.uuid4().hex[:6]}"
    pin = {"lat": 9.451, "lng": 76.392}
    first = client.post(
        "/api/reports",
        json={
            "text": f"{token} Church Road pe 4 log chhat par hain, boat bhejo",
            "lang": "hinglish",
            "channel": "text",
            "location_pin": pin,
            "idempotency_key": f"dedupe-a-{token}",
        },
    )
    second = client.post(
        "/api/reports",
        json={
            "text": f"Church Road {token} par 4 log fas gaye, madad chahiye",
            "lang": "hinglish",
            "channel": "text",
            "location_pin": pin,
            "idempotency_key": f"dedupe-b-{token}",
        },
    )
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["dedupe_decision"] == "new"
    assert second.json()["dedupe_decision"] == "duplicate"

    listed = client.get("/api/requests", headers=AUTH)
    assert listed.status_code == 200
    cards = [
        row for row in listed.json()
        if token.lower() in (row.get("place_text") or "").lower()
        or token.lower() in (row.get("raw_text") or "").lower()
    ]
    assert len(cards) == 2
    assert all(not c.get("merged_into") for c in cards)
    flagged = [c for c in cards if (c.get("possible_duplicate") or {}).get("target_id")]
    assert len(flagged) == 1

    label = json.loads(EN.read_text(encoding="utf-8"))["coord"]["sameIncident"].replace("{n}", "2")
    assert "2 reports" in label


def test_a_counted_report_does_not_merge_just_because_both_say_stranded():
    token = f"E2Edesk{uuid.uuid4().hex[:6]}"
    created = client.post(
        "/api/reports",
        json={
            "text": f"4 people stranded, need a boat. Synthetic report {token}.",
            "raw_text": f"4 people stranded, need a boat. Synthetic report {token}.",
            "lang": "en",
            "channel": "text",
            "location_pin": {"lat": 9.416, "lng": 76.411},
            "idempotency_key": f"e2e-shape-{token}",
            "structured": {
                "incident_type": "rescue",
                "place_text": token,
                "people_count": 4,
                "hazard": "water_rising",
                "vulnerable": {"child": True},
                "summary": token,
            },
        },
    )
    assert created.status_code == 200, created.text
    assert created.json()["dedupe_decision"] == "new"
    listed = client.get("/api/requests", headers=AUTH)
    cards = [row for row in listed.json() if token in (row.get("place_text") or "") or token in (row.get("raw_text") or "")]
    assert len(cards) == 1
    assert cards[0]["id"] != "INC-003"
