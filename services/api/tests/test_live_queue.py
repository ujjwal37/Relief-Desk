"""A coordinator poll can ask only for rows changed since the last read."""
from fastapi.testclient import TestClient
from app.main import app
from app.tools.storage import storage_service

client = TestClient(app)
AUTH = {"Authorization": "Bearer demo-coordinator-token"}


def test_updated_since_includes_a_new_report_and_skips_older_ones():
    storage_service.load_seed_incidents()
    before = client.get("/api/requests", headers=AUTH)
    assert before.status_code == 200
    rows = before.json()
    assert rows
    watermark = max(row["updated_at"] for row in rows)

    created = client.post(
        "/api/reports",
        json={
            "text": "Live queue check: 2 people on a roof in Ward 4",
            "channel": "text",
            "lang": "en",
            "idempotency_key": "idem_live_queue_probe",
            "location_pin": {"lat": 26.85, "lng": 80.94},
        },
    )
    assert created.status_code == 200
    new_id = created.json()["request_id"]

    polled = client.get("/api/requests", params={"updated_since": watermark}, headers=AUTH)
    assert polled.status_code == 200
    ids = [row["id"] for row in polled.json()]
    assert new_id in ids
    assert all(row["updated_at"] >= watermark for row in polled.json())
