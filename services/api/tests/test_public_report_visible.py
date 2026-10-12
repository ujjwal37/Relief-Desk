"""A public report must show up for the demo coordinator, including a northern ward."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
AUTH = {"Authorization": "Bearer demo-coordinator-token"}


def test_public_report_is_in_the_next_poll_even_if_the_plus_was_eaten():
    before = client.get("/api/requests", headers=AUTH)
    assert before.status_code == 200
    rows = before.json()
    assert rows
    watermark = max(row["updated_at"] for row in rows)

    created = client.post(
        "/api/reports",
        json={
            "text": "House 19 on Temple Road, Chalakudy. 40 people on the roof need a boat. Synthetic live report UX8.",
            "raw_text": "House 19 on Temple Road, Chalakudy. 40 people on the roof need a boat. Synthetic live report UX8.",
            "channel": "text",
            "lang": "en",
            "scenario_id": "flood",
            "idempotency_key": "idem_ux8_visible_ward7",
            "location_pin": {"lat": 10.308, "lng": 76.331},
            "structured": {
                "incident_type": "rescue",
                "place_text": "Chalakudy temple road house 19",
                "people_count": 40,
                "hazard": "water_rising",
                "vulnerable": {"child": True},
                "summary": "40 people on a roof in Ward 7",
            },
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    new_id = body["request_id"]
    assert body["dedupe_decision"] != "duplicate"

    # A query string can turn '+' into a space. The row must still be returned.
    broken = watermark.replace("+", " ")
    polled = client.get("/api/requests", params={"updated_since": broken, "pack_id": "flood"}, headers=AUTH)
    assert polled.status_code == 200
    ids = [row["id"] for row in polled.json()]
    assert new_id in ids

    listed = client.get("/api/requests", params={"pack_id": "flood"}, headers=AUTH)
    found = next(row for row in listed.json() if row["id"] == new_id)
    assert found["ward_id"] == "ward_7"

    desk = client.post(
        "/api/desk/ask",
        json={"question": "40 people rescue in Chalakudy still waiting"},
        headers=AUTH,
    )
    assert desk.status_code == 200
    body = desk.json()
    assert body["filters"]["ward_ids"] == ["ward_7"]
    assert new_id in [row["id"] for row in body["cases"]]
