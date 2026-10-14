"""Offline retries must not create a second request."""
from fastapi.testclient import TestClient
from app.main import app
from app.tools.storage import storage_service

client = TestClient(app)


def test_same_idempotency_key_returns_the_original_request():
    payload = {
        "text": "3 people stranded at Ward 7 Temple Road, one child",
        "channel": "text",
        "lang": "en",
        "idempotency_key": "idem_offline_once",
        "location_pin": {"lat": 9.498, "lng": 76.338},
    }
    before = len(storage_service.list_requests())
    first = client.post("/api/reports", json=payload)
    second = client.post("/api/reports", json=payload)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["request_id"] == second.json()["request_id"]
    assert first.json()["report_id"] == second.json()["report_id"]
    assert first.json()["status_token"] == second.json()["status_token"]
    assert len(storage_service.list_requests()) == before + 1
