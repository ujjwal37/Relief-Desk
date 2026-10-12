"""Live GPS, demo movement, privacy, and the free/busy assignment loop."""
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.agents.dispatcher import find_teams, propose_assignment
from app.agents.matching import matching_agent
from app.main import app
from app.models.firestore_models import (
    RequestStatus,
    ResourceKind,
    ResourceStatus,
    StoredReport,
    StoredRequest,
)
from app.models.schemas import IncidentType
from app.tools.storage import storage_service
from app.tracking.availability import candidate_kind, needs_check_in
from app.tracking.live import SPEED_KMH, clear_rate_limits, live_eta
from app.tracking.tokens import team_share_token

client = TestClient(app)
AUTH = {"Authorization": "Bearer demo-coordinator-token"}


def _boat(resource_id: str = "RES-BOAT-01"):
    storage_service.load_seed_resources()
    boat = storage_service.get_resource(resource_id)
    assert boat is not None
    return boat


def test_live_eta_uses_type_speed_and_the_30_km_cap():
    minutes, far = live_eta(1.8, "boat")
    assert minutes == 6
    assert far is False
    assert SPEED_KMH["medical"] > SPEED_KMH["boat"]
    medical, _ = live_eta(1.8, "medical")
    assert medical is not None and medical < minutes
    none, no_nearby = live_eta(31, "boat")
    assert none is None
    assert no_nearby is True


def test_location_requires_the_team_token_and_rejects_a_jump_and_a_burst():
    boat = _boat()
    token = team_share_token(boat.id)
    clear_rate_limits()
    missing = client.post(f"/api/teams/{boat.id}/location", json={"lat": 9.5, "lng": 76.4})
    assert missing.status_code == 401
    wrong = client.post(
        f"/api/teams/{boat.id}/location",
        json={"lat": 9.5, "lng": 76.4, "token": "tm_not-the-token"},
    )
    assert wrong.status_code == 401
    ok = client.post(
        f"/api/teams/{boat.id}/location",
        json={"lat": 9.5, "lng": 76.4, "accuracy": 18, "heading": 90, "speed": 4.2, "ts": datetime.now(timezone.utc).isoformat(), "token": token},
    )
    assert ok.status_code == 200
    body = ok.json()
    assert body["location_source"] == "gps"
    assert body["simulated"] is False
    assert body["accuracy_m"] == 18
    burst = client.post(
        f"/api/teams/{boat.id}/location",
        json={"lat": 9.501, "lng": 76.401, "token": token},
    )
    assert burst.status_code == 429

    clear_rate_limits()
    jump = client.post(
        f"/api/teams/{boat.id}/location",
        json={
            "lat": 11.6,
            "lng": 75.5,
            "token": token,
            "ts": (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat(),
        },
    )
    assert jump.status_code == 422
    assert storage_service.get_resource(boat.id).lat == 9.5


def test_position_is_stale_after_two_minutes_and_eta_follows_the_live_point():
    boat = _boat("RES-BOAT-02")
    req = StoredRequest(
        id="req_live_eta",
        type=IncidentType.RESCUE,
        status=RequestStatus.DISPATCHED,
        assigned_resource_id=boat.id,
        lat=boat.lat + 0.02,
        lng=boat.lng,
        people_count=2,
    )
    storage_service.save_request(req, actor="test")
    boat.assigned_request_id = req.id
    boat.status = ResourceStatus.DISPATCHED
    boat.location_source = "gps"
    boat.location_updated_at = datetime.now(timezone.utc).isoformat()
    storage_service._resources[boat.id] = boat

    fresh = client.get("/api/teams/locations", headers=AUTH)
    assert fresh.status_code == 200
    row = next(item for item in fresh.json()["teams"] if item["id"] == boat.id)
    assert row["stale"] is False
    assert row["eta_minutes"] is not None
    assert row["no_nearby"] is False
    first_eta = row["eta_minutes"]

    boat.lat = req.lat - 0.005
    boat.location_updated_at = datetime.now(timezone.utc).isoformat()
    closer = next(item for item in client.get("/api/teams/locations", headers=AUTH).json()["teams"] if item["id"] == boat.id)
    assert closer["eta_minutes"] < first_eta

    boat.location_updated_at = (datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat()
    stale = next(item for item in client.get("/api/teams/locations", headers=AUTH).json()["teams"] if item["id"] == boat.id)
    assert stale["stale"] is True
    assert client.get("/api/teams/locations").status_code == 401
    req.status = RequestStatus.COMPLETED
    req.assigned_resource_id = None
    storage_service.save_request(req, actor="test")


def test_citizen_tracking_is_token_gated_and_stops_at_completion():
    storage_service.load_seed_resources()
    other = storage_service.list_resources(kind=ResourceKind.MEDICAL)[0]
    boat = storage_service.get_resource("RES-BOAT-03")
    assert boat is not None
    report = storage_service.save_report_raw(
        "Synthetic roof report", source_id="device_x", pack_id="flood", status_token="tok_citizen_track"
    )
    report = storage_service.get_report(report.id)
    assert isinstance(report, StoredReport)
    req = StoredRequest(
        id="req_citizen_track",
        type=IncidentType.RESCUE,
        status=RequestStatus.NEW,
        lat=boat.lat + 0.016,
        lng=boat.lng,
        people_count=2,
    )
    storage_service.save_request(req, actor="test")
    report.request_id = req.id
    storage_service._reports[report.id] = report
    token = report.status_token

    denied = client.get(f"/api/reports/{report.id}/tracking")
    assert denied.status_code == 401
    waiting = client.get(f"/api/reports/{report.id}/tracking?token={token}").json()
    assert waiting["visible"] is False
    assert waiting["lat"] is None
    assert boat.name not in str(waiting)
    assert other.name not in str(waiting)

    req.status = RequestStatus.DISPATCHED
    req.assigned_resource_id = boat.id
    boat.assigned_request_id = req.id
    boat.status = ResourceStatus.EN_ROUTE
    boat.location_source = "simulated"
    boat.simulated = True
    boat.location_updated_at = datetime.now(timezone.utc).isoformat()
    live = client.get(f"/api/reports/{report.id}/tracking?token={token}").json()
    assert live["visible"] is True
    assert live["state"] == "dispatched"
    assert live["team_name"] == boat.name
    assert live["lat"] == boat.lat
    assert live["simulated"] is True
    assert other.name not in client.get(f"/api/reports/{report.id}/tracking?token={token}").text
    assert "capacity" not in live

    req.status = RequestStatus.COMPLETED
    done = client.get(f"/api/reports/{report.id}/tracking?token={token}").json()
    assert done["state"] == "completed"
    assert done["lat"] is None
    assert done["lng"] is None


def test_status_loop_sets_busy_on_dispatch_and_frees_capacity_on_completion():
    storage_service.load_seed_resources()
    boat = storage_service.get_resource("RES-BOAT-01")
    assert boat is not None
    seats = boat.capacity_remaining
    req = StoredRequest(
        id="req_status_loop",
        type=IncidentType.RESCUE,
        status=RequestStatus.NEW,
        lat=boat.lat + 0.03,
        lng=boat.lng,
        people_count=2,
    )
    storage_service.save_request(req, actor="test")
    from app.models.firestore_models import MatchBreakdown, MatchState, StoredMatch

    match = StoredMatch(
        id="match_status_loop",
        request_id=req.id,
        resource_id=boat.id,
        score=80,
        breakdown=MatchBreakdown(
            distance_km=3, distance_score=20, capacity_fit_score=25, urgency_score=20, vulnerability_fit_score=15, total_score=80
        ),
        state=MatchState.PROPOSED,
    )
    storage_service.save_match(match, actor="test")
    approved = client.post(f"/api/matches/{match.id}/approve", headers=AUTH, json={})
    assert approved.status_code == 200
    busy = storage_service.get_resource(boat.id)
    assert busy is not None
    assert busy.status == ResourceStatus.DISPATCHED
    assert busy.busy_since
    assert candidate_kind(busy) is None
    assert busy.capacity_remaining == seats - 2

    token = team_share_token(boat.id)
    assert client.post(f"/api/teams/{boat.id}/status", json={"action": "accept", "token": token}).status_code == 200
    assert storage_service.get_resource(boat.id).status == ResourceStatus.ACCEPTED
    assert client.post(f"/api/teams/{boat.id}/status", json={"action": "on_the_way", "token": token}).status_code == 200
    assert client.post(f"/api/teams/{boat.id}/status", json={"action": "arrived", "token": token}).status_code == 200
    assert storage_service.get_request(req.id).status == RequestStatus.IN_PROGRESS
    done = client.post(
        f"/api/teams/{boat.id}/status",
        json={"action": "complete", "token": token, "people_helped": 2, "needs_follow_up": False},
    )
    assert done.status_code == 200
    free = done.json()
    assert free["status"] == "available"
    assert free["assigned_request_id"] is None
    assert free["capacity_remaining"] == seats
    assert storage_service.get_request(req.id).status == RequestStatus.COMPLETED
    audit = storage_service.get_audit_trail(boat.id)
    outcome = [row for row in audit if row.action == "team_complete"]
    assert outcome
    assert outcome[-1].after["people_helped"] == 2
    assert outcome[-1].after["needs_follow_up"] is False
    assert candidate_kind(storage_service.get_resource(boat.id)) == "free"


def test_check_in_and_coordinator_override():
    boat = _boat("RES-BOAT-04")
    boat.status = ResourceStatus.DISPATCHED
    old = (datetime.now(timezone.utc) - timedelta(minutes=11)).isoformat()
    boat.location_updated_at = old
    boat.status_changed_at = old
    boat.busy_since = old
    boat.location_source = "gps"
    assert needs_check_in(boat) is True
    boat.location_updated_at = datetime.now(timezone.utc).isoformat()
    assert needs_check_in(boat) is False

    overridden = client.post(
        f"/api/teams/{boat.id}/override",
        headers=AUTH,
        json={"status": "available", "reason": "Team called in by radio"},
    )
    assert overridden.status_code == 200
    assert overridden.json()["status"] == "available"
    assert any(row.action == "team_override" for row in storage_service.get_audit_trail(boat.id))
    assert client.post(f"/api/teams/{boat.id}/override", headers=AUTH, json={"status": "available", "reason": "no"}).status_code == 422


def test_matching_skips_busy_and_stale_teams_and_can_offer_one_finishing_soon():
    storage_service.load_seed_resources()
    boats = storage_service.list_resources(kind=ResourceKind.BOAT)
    keeper = boats[0]
    for boat in boats[1:]:
        boat.status = ResourceStatus.BUSY
    keeper.status = ResourceStatus.AVAILABLE
    keeper.location_source = "gps"
    keeper.location_updated_at = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    req = StoredRequest(
        id="req_stale_match",
        type=IncidentType.RESCUE,
        lat=keeper.lat,
        lng=keeper.lng,
        people_count=2,
        urgency_score=80,
    )
    storage_service.save_request(req, actor="test")
    stale_proposals = matching_agent.find_matches(req, top_n=3, save_to_storage=False)
    assert all(row.resource_kind != ResourceKind.BOAT or row.is_fallback for row in stale_proposals)
    assert all(row.resource_id != keeper.id for row in stale_proposals)

    keeper.location_updated_at = datetime.now(timezone.utc).isoformat()
    keeper.status = ResourceStatus.ON_SCENE
    keeper.status_changed_at = (datetime.now(timezone.utc) - timedelta(minutes=9)).isoformat()
    keeper.capacity_remaining = keeper.capacity_total
    soon = matching_agent.find_matches(req, top_n=3, save_to_storage=False)
    offer = next(row for row in soon if row.resource_id == keeper.id)
    assert offer.soon_free is True
    assert "finishing soon" in (offer.explanation or "")
    assert "km away" in (offer.explanation or "")
    ranked = find_teams("boat", keeper.lat, keeper.lng)
    assert ranked
    assert ranked[0]["id"] == keeper.id
    assert "finishing soon" in ranked[0]["note"]
    refused = propose_assignment(req.id, boats[1].id)
    assert refused["ok"] is False


def test_demo_step_is_labelled_simulated_and_moves_toward_the_case():
    boat = _boat("RES-BOAT-01")
    origin = boat.lat
    from app.tracking.simulate import arm_demo_route, step_all

    arm_demo_route(boat.id, boat.lat + 0.05, boat.lng)
    boat.status = ResourceStatus.DISPATCHED
    moved = step_all()
    assert moved
    assert moved[0]["simulated"] is True
    assert moved[0]["source"] == "simulated"
    assert storage_service.get_resource(boat.id).lat != origin
    assert client.post("/api/demo/tracking/step", headers=AUTH).status_code == 200
