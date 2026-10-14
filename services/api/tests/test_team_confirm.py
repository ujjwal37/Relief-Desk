"""No team free: estimated wait, resource gap, field confirm, and a movement trail."""
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app
from app.models.firestore_models import RequestStatus, ResourceKind, ResourceStatus, StoredRequest
from app.models.schemas import IncidentType
from app.tools.anomaly import live_alerts_from_storage
from app.tools.storage import storage_service

client = TestClient(app)


def test_seeded_cases_are_inside_the_last_hour():
    rows = [row for row in storage_service.list_requests() if str(row.id).startswith("INC-")]
    assert len(rows) >= 40
    now = datetime.now(timezone.utc)
    for row in rows:
        created = datetime.fromisoformat(row.created_at)
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age = (now - created).total_seconds()
        assert 0 <= age < 3600


def test_resource_gap_when_no_suitable_team_is_free():
    storage_service.load_seed_resources()
    try:
        for boat in storage_service.list_resources(kind=ResourceKind.BOAT):
            boat.status = ResourceStatus.BUSY
        alerts = live_alerts_from_storage(storage_service)
        gap = [item for item in alerts if item.id == "gap-none-boat"]
        assert gap
        assert gap[0].kind == "resource_gap"
        assert gap[0].title == "Resource gap"
    finally:
        storage_service.load_seed_resources()


def test_team_confirm_updates_status_and_keeps_a_trail():
    storage_service.load_seed_resources()
    boat = storage_service.list_resources(kind=ResourceKind.BOAT)[0]
    req = StoredRequest(
        id="req_team_confirm",
        type=IncidentType.RESCUE,
        status=RequestStatus.DISPATCHED,
        assigned_resource_id=boat.id,
        people_count=2,
        lat=boat.lat + 0.02,
        lng=boat.lng + 0.02,
    )
    storage_service.save_request(req, actor="test")
    boat.assigned_request_id = req.id
    boat.status = ResourceStatus.DISPATCHED
    storage_service.begin_simulation(boat.id, req.lat, req.lng, launch=False)
    storage_service.step_simulation(boat.id)
    moving = storage_service.get_resource(boat.id)
    assert moving is not None
    assert moving.simulated is True
    assert len(moving.location_trail) >= 2

    arrived = storage_service.team_action(boat.id, "at_scene")
    assert arrived.status == ResourceStatus.ON_SCENE
    assert arrived.simulated is False
    assert storage_service.get_request(req.id).status == RequestStatus.IN_PROGRESS

    done = storage_service.team_action(boat.id, "done")
    assert done.status == ResourceStatus.RETURNING
    assert storage_service.get_request(req.id).status == RequestStatus.COMPLETED

    back = storage_service.team_action(boat.id, "available")
    assert back.status == ResourceStatus.AVAILABLE
    assert back.assigned_request_id is None


def test_team_confirm_link_is_public():
    storage_service.load_seed_resources()
    boat = storage_service.list_resources(kind=ResourceKind.BOAT)[0]
    found = client.get(f"/api/team/{boat.id}")
    assert found.status_code == 200
    assert found.json()["id"] == boat.id
    missing = client.post(f"/api/team/{boat.id}", json={"action": "nope"})
    assert missing.status_code == 400
