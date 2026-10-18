import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.tools.storage import storage_service

client = TestClient(app)


def test_post_report_without_place_then_demo_pin_resolves_ward_and_clears_location_needed():
    # 1. Post a report with no typed place
    payload = {
        "text": "Water is rising quickly, 4 people trapped on first floor, send help immediately",
        "raw_text": "Water is rising quickly, 4 people trapped on first floor, send help immediately",
        "lang": "en",
        "channel": "text",
        "source_id": "test_device_demo_loc",
    }
    res = client.post("/api/reports", json=payload)
    assert res.status_code == 200, res.text
    data = res.json()
    report_id = data["report_id"]
    token = data["status_token"]
    request_id = data["request_id"]
    assert report_id and token and request_id

    # 2. Status initially shows location is needed (place_stated is False)
    status_res1 = client.get(f"/api/reports/{report_id}/status?token={token}")
    assert status_res1.status_code == 200, status_res1.text
    status_data1 = status_res1.json()
    assert status_data1["place_stated"] is False
    assert status_data1["demo_location"] is False

    # Check stored request has no lat/lng before location update
    req_before = storage_service.get_request(request_id)
    assert req_before is not None
    assert req_before.lat is None
    assert req_before.lng is None
    # Location needed banner condition in coordinator: (!req.lat || !req.lng)
    assert (not req_before.lat or not req_before.lng) is True

    # 3. Share demo pin: Kainakary jetty (lat 9.47185, lng 76.39571)
    loc_payload = {
        "token": token,
        "lat": 9.47185,
        "lng": 76.39571,
        "accuracy": 25,
        "location_source": "demo_pin",
    }
    loc_res = client.post(f"/api/reports/{report_id}/location", json=loc_payload)
    assert loc_res.status_code == 200, loc_res.text
    loc_data = loc_res.json()
    assert loc_data["ok"] is True
    assert loc_data["lat"] == 9.47185
    assert loc_data["lng"] == 76.39571
    assert loc_data["source"] == "demo_pin"
    assert loc_data["demo_location"] is True

    # 4. Status now has place_stated True (no location-needed state) and demo_location True
    status_res2 = client.get(f"/api/reports/{report_id}/status?token={token}")
    assert status_res2.status_code == 200, status_res2.text
    status_data2 = status_res2.json()
    assert status_data2["place_stated"] is True
    assert status_data2["demo_location"] is True
    assert status_data2["location_source"] == "demo_pin"

    # 5. Stored request has coordinates, ward_1, demo_location flag, and no location-needed state
    req_after = storage_service.get_request(request_id)
    assert req_after is not None
    assert req_after.lat == 9.47185
    assert req_after.lng == 76.39571
    assert req_after.ward_id == "ward_1"
    assert req_after.demo_location is True
    assert req_after.location_source == "demo_pin"
    # Coordinator location-needed line condition (!req.lat || !req.lng) must not show
    assert (not req_after.lat or not req_after.lng) is False


def test_post_demo_pin_round_robin_points_resolve_kuttanad_wards():
    # Test second point: Nedumudi (lat 9.43, lng 76.398) -> ward_3
    payload = {
        "text": "Elderly patient needs medicine urgently",
        "lang": "en",
        "channel": "text",
        "source_id": "test_device_demo_loc_2",
    }
    res = client.post("/api/reports", json=payload)
    assert res.status_code == 200
    data = res.json()
    report_id = data["report_id"]
    token = data["status_token"]
    request_id = data["request_id"]

    loc_payload = {
        "token": token,
        "lat": 9.43,
        "lng": 76.398,
        "accuracy": 25,
        "location_source": "demo_pin",
    }
    loc_res = client.post(f"/api/reports/{report_id}/location", json=loc_payload)
    assert loc_res.status_code == 200

    req = storage_service.get_request(request_id)
    assert req is not None
    assert req.lat == 9.43
    assert req.lng == 76.398
    assert req.ward_id == "ward_3"
    assert req.demo_location is True
    assert req.location_source == "demo_pin"
