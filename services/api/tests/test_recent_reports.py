"""Just reported: the last 15 minutes, newest first, with a merge flag."""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.main import app
from app.models.firestore_models import StoredReport
from app.tools.storage import storage_service

client = TestClient(app)
AUTH = {"Authorization": "Bearer demo-coordinator-token"}


def test_recent_reports_are_newest_first_and_skip_older_ones():
    now = datetime.now(timezone.utc)
    older = StoredReport(
        id="rep_just_old",
        raw_text="older ferry report",
        created_at=(now - timedelta(minutes=5)).isoformat(),
        case_id="INC-OLD",
        incident_type="rescue",
        summary="Water at the ferry",
        place_text="Kainakary",
        ward_id="ward_1",
        joined_existing=False,
    )
    newer = StoredReport(
        id="rep_just_new",
        raw_text="newer ferry report",
        created_at=(now - timedelta(minutes=1)).isoformat(),
        case_id="INC-OLD",
        incident_type="rescue",
        summary="Water still rising",
        place_text="Kainakary",
        ward_id="ward_1",
        joined_existing=True,
    )
    stale = StoredReport(
        id="rep_just_stale",
        raw_text="stale",
        created_at=(now - timedelta(minutes=40)).isoformat(),
        case_id="INC-STALE",
        incident_type="food",
        summary="old food report",
    )
    storage_service._reports[older.id] = older
    storage_service._reports[newer.id] = newer
    storage_service._reports[stale.id] = stale

    listed = client.get("/api/recent-reports", headers=AUTH)
    assert listed.status_code == 200
    rows = listed.json()
    ids = [row["id"] for row in rows]
    assert ids.index("rep_just_new") < ids.index("rep_just_old")
    assert "rep_just_stale" not in ids
    merged = next(row for row in rows if row["id"] == "rep_just_new")
    assert merged["joined_existing"] is True
    assert merged["case_id"] == "INC-OLD"
    assert merged["type"] == "rescue"
    assert merged["ward_id"] == "ward_1"
    assert merged["place_text"] == "Kainakary"


def test_submit_stamps_the_report_the_strip_reads():
    token = f"Tipsyard{uuid.uuid4().hex[:6]}"
    created = client.post(
        "/api/reports",
        json={
            "text": f"Father needs medicine at {token}. One person.",
            "channel": "form",
            "lang": "en",
            "source_id": f"just_{token}",
            "scenario_id": "flood",
            "location_pin": {"lat": 8.21, "lng": 77.91},
            "structured": {
                "incident_type": "medical",
                "place_text": token,
                "people_count": 1,
                "hazard": "none",
                "summary": f"Medicine at {token}",
            },
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    listed = client.get("/api/recent-reports", headers=AUTH)
    row = next(item for item in listed.json() if item["id"] == body["report_id"])
    assert row["type"] == "medical"
    assert row["joined_existing"] is False
    assert row["case_id"] == body["request_id"]
    assert token in row["summary"]
    assert row["place_text"] == token
