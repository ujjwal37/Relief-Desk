from fastapi.testclient import TestClient

from app.api.reports import build_receipt
from app.main import app
from app.models.firestore_models import StoredReport, StoredRequest
from app.models.schemas import HazardType, IncidentType
from app.tools.case_queue import begin_case, life_phrase
from app.tools.storage import storage_service


def test_oxygen_cylinder_gets_lifethreat_flag():
    text = "oxygen cylinder finishing in 1 hour, COPD patient, Nedumudi ward 3"
    # (a) life_phrase matches and begin_case attaches the lifeThreat flag to ai_queue
    phrase = life_phrase(text)
    assert phrase is not None

    req = StoredRequest(
        id="req_oxygen_test",
        type=IncidentType.MEDICAL,
        raw_text=text,
        place_text="Nedumudi ward 3",
    )
    queue = begin_case(req, text, others=[])
    assert queue is not None
    assert "lifeThreat" in queue.flags
    assert req.ai_queue is not None
    assert "lifeThreat" in req.ai_queue.flags

    client = TestClient(app)
    resp = client.post(
        "/api/reports",
        json={
            "text": text,
            "channel": "text",
            "lang": "en",
            "source_id": "test_oxygen_selftest",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    saved = storage_service.get_request(data["request_id"])
    assert saved is not None
    assert saved.ai_queue is not None
    assert "lifeThreat" in saved.ai_queue.flags


def test_forward_dam_broke_gets_hoax_flag():
    # (b) Forward to all: Mullaperiyar dam broke, everyone evacuate now, army says so gets the hoax flag via POST /api/reports
    client = TestClient(app)
    hoax_text = "Forward to all: Mullaperiyar dam broke, everyone evacuate now, army says so"
    resp = client.post(
        "/api/reports",
        json={
            "text": hoax_text,
            "channel": "text",
            "lang": "en",
            "source_id": "test_hoax_selftest",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "hoax" in data["flags"]


def test_genuine_mullaperiyar_dam_report_not_hoax():
    # (c) Water entered near Mullaperiyar dam road, 3 people stranded, Kumily is NOT a hoax
    client = TestClient(app)
    genuine_text = "Water entered near Mullaperiyar dam road, 3 people stranded, Kumily"
    resp = client.post(
        "/api/reports",
        json={
            "text": genuine_text,
            "channel": "text",
            "lang": "en",
            "source_id": "test_genuine_selftest",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "hoax" not in data["flags"]
    assert "likely_hoax" not in data["flags"]


def test_build_receipt_without_hazard_in_text_does_not_contain_water_rising():
    # (d) build_receipt for a request with no hazard in text does not contain water rising
    text_nohazard = "Need food packets for 4 people, elderly person, Nedumudi ward 3"
    req_obj = StoredRequest(
        id="req_nohazard_receipt",
        type=IncidentType.FOOD,
        raw_text=text_nohazard,
        place_text="Nedumudi ward 3",
        people_count=4,
        hazard=HazardType.WATER_RISING,  # e.g. set by fallback/model artifact
    )
    raw_report = StoredReport(
        id="rep_nohazard_receipt",
        raw_text=text_nohazard,
        lang="en",
    )
    receipt = build_receipt(req_obj, raw_report, "RD-1001")
    assert "water rising" not in receipt.lower()

    # Empty text case (such as a dashboard screenshot with no hazard text or photo facts)
    req_empty = StoredRequest(
        id="req_empty_receipt",
        type=IncidentType.OTHER,
        raw_text="",
        hazard=HazardType.WATER_RISING,
        photo_facts=[],
    )
    raw_report_empty = StoredReport(
        id="rep_empty_receipt",
        raw_text="",
        lang="en",
    )
    receipt_empty = build_receipt(req_empty, raw_report_empty, "RD-1002")
    assert "water rising" not in receipt_empty.lower()

    # Via POST /api/reports with fallback model
    client = TestClient(app)
    resp = client.post(
        "/api/reports",
        json={
            "text": "10 food packets needed urgently at Aluva community hall",
            "channel": "text",
            "lang": "en",
            "source_id": "test_nohazard_receipt_api",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    receipt_api = data.get("receipt") or ""
    assert "water rising" not in receipt_api.lower()
