import re
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.models.firestore_models import StoredRequest, RequestStatus, StoredReport
from app.tools.storage import storage_service

client = TestClient(app)


def test_public_cells_privacy_contract():
    """CRITICAL ACCEPTANCE CRITERIA:
    No names, phones, exact addresses, or raw report text in /api/public/cells response."""
    # First seed a request with a raw report and synthetic phone/name in storage to test leakage prevention
    rep = storage_service.save_report_raw(
        raw_text="Emergency! Ramesh Kumar phone 9876543210 at House 42 River St Ward 7 needs rescue immediately",
        source_id="device_secret_999",
        pack_id="flood",
    )
    req = StoredRequest(
        id="req_privacy_check_1",
        place_text="House 42 River St, Ward 7",
        ward_id="Ward 7",
        lat=26.85212345,  # exact high-precision coordinate
        lng=80.93123456,
        people_count=4,
        status=RequestStatus.NEW,
        raw_text="Ramesh Kumar 9876543210",
        flags=[],
    )
    storage_service.save_request(req, actor="test")

    response = client.get("/api/public/cells")
    assert response.status_code == 200
    data = response.json()

    assert "cells" in data
    assert len(data["cells"]) >= 4
    assert data["synthetic"] is True
    assert "disclaimer" in data

    # 1. Check raw text payload for forbidden strings
    raw_response_str = response.text
    forbidden_tokens = [
        "Ramesh", "Kumar", "9876543210", "House 42", "River St",
        "device_secret_999", "raw_text", "phone_hash"
    ]
    for token in forbidden_tokens:
        assert token.lower() not in raw_response_str.lower(), f"PII leaked: {token} found in /api/public/cells"

    # 2. Check regex phone pattern
    phone_pattern = re.compile(r"\b\d{10}\b")
    assert not phone_pattern.search(raw_response_str), "Phone number pattern matched in public cells response!"

    # 3. Check every cell object for strictly permitted fields only
    allowed_keys = {
        "cell_id", "ward", "center_lat", "center_lng", "incident_counts",
        "total_reports", "severity_band", "time_bucket", "active_hazard",
        "alerts", "last_updated"
    }
    for cell in data["cells"]:
        cell_keys = set(cell.keys())
        unexpected = cell_keys - allowed_keys
        assert not unexpected, f"Unexpected sensitive fields in PublicCell: {unexpected}"
        # Verify coordinates are coarse (rounded to max 4 decimal places)
        lat_str = str(cell["center_lat"])
        lng_str = str(cell["center_lng"])
        if "." in lat_str:
            assert len(lat_str.split(".")[1]) <= 4
        if "." in lng_str:
            assert len(lng_str.split(".")[1]) <= 4


def test_public_cells_bbox_filter():
    response = client.get("/api/public/cells?bbox=76.00,9.30,76.70,11.70")
    assert response.status_code == 200
    data = response.json()
    assert len(data["cells"]) > 0


def test_public_alerts_endpoint():
    response = client.get("/api/public/alerts")
    assert response.status_code == 200
    alerts = response.json()
    assert len(alerts) >= 3
    assert any(a["id"] == "alt_01" for a in alerts)
    assert any("Ward 9" in a["ward"] for a in alerts)


def test_demo_report_status():
    """Verify demo status lookup matches public-04-status.html."""
    response = client.get("/api/reports/R-0412/status?token=tok_demo")
    assert response.status_code == 200
    data = response.json()

    assert data["report_id"] == "R-0412"
    assert data["request_id"] == "REQ-0412"
    assert "Sent. Help is being arranged." in data["hero_title"]
    assert data["eta_display"] == "~18 min"
    assert data["emergency_phone"] == "112"
    assert len(data["timeline"]) == 4
    assert data["timeline"][0]["name"] == "received"
    assert data["timeline"][0]["state"] == "done"
    assert data["timeline"][1]["name"] == "matched"
    assert data["timeline"][1]["state"] == "done"
    assert data["timeline"][2]["name"] == "on_the_way"
    assert data["timeline"][2]["state"] == "current"
    assert data["timeline"][3]["name"] == "fulfilled"
    assert data["timeline"][3]["state"] == "pending"
    assert len(data["while_you_wait_tips"]) == 3


def test_submitted_report_status_lifecycle():
    """Submit a real report through POST /api/reports and follow its status lifecycle."""
    submit_res = client.post(
        "/api/reports",
        json={
            "text": "Paani bohot tez badh raha hai, 4 log fase hain Ward 7 mein",
            "channel": "text",
            "lang": "hi",
            "source_id": "test_reporter_device",
            "location_pin": {"lat": 26.852, "lng": 80.931},
            "scenario_id": "flood"
        }
    )
    assert submit_res.status_code == 200
    submit_data = submit_res.json()
    report_id = submit_data["report_id"]
    token = submit_data["status_token"]

    status_res = client.get(f"/api/reports/{report_id}/status?token={token}")
    assert status_res.status_code == 200
    status_data = status_res.json()

    assert status_data["report_id"] == report_id
    assert status_data["status"] == "new"
    assert status_data["timeline"][0]["state"] == "done"
    assert status_data["timeline"][1]["state"] == "pending"
    assert status_data["timeline"][2]["state"] == "pending"
    assert status_data["eta_minutes"] is None
    assert status_data["public_code"].startswith("RD-")
    assert "प्राप्त" not in status_res.text
    assert "112" in status_data["emergency_phone"]

    # Verify no PII in status output
    raw_str = status_res.text
    assert "test_reporter_device" not in raw_str
    assert "Paani bohot tez" not in raw_str  # Raw report text not exposed in public status


def test_report_status_not_found():
    response = client.get("/api/reports/nonexistent_99999/status?token=bad_token")
    assert response.status_code == 404
