from fastapi.testclient import TestClient
from app.main import app
from app.models.firestore_models import StoredRequest, RequestStatus
from app.models.schemas import IncidentType, HazardType, VulnerableFlags
from app.tools.storage import storage_service

client = TestClient(app)
AUTH_HEADERS = {"Authorization": "Bearer demo-coordinator-token"}


def test_matches_api_auth_required():
    resp = client.get("/api/requests/req_fake/matches")
    assert resp.status_code == 401


def test_get_request_matches_proposals_breakdown():
    storage_service.load_seed_resources()

    req = StoredRequest(
        id="req_match_agent_test",
        type=IncidentType.RESCUE,
        lat=26.852,
        lng=80.940,
        people_count=6,
        hazard=HazardType.WATER_RISING,
        urgency_score=88.0,
        vulnerable=VulnerableFlags(child=True, elderly=True),
        status=RequestStatus.NEW,
    )
    storage_service.save_request(req, actor="test")

    resp = client.get(f"/api/requests/{req.id}/matches", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    proposals = resp.json()

    # Acceptance criteria: Returns >= 2 proposals
    assert len(proposals) >= 2

    # Acceptance criteria: distance/capacity/urgency/vulnerability parts sum to score
    for p in proposals:
        b = p["breakdown"]
        parts_sum = round(
            b["distance_score"]
            + b["capacity_fit_score"]
            + b["urgency_score"]
            + b["vulnerability_fit_score"],
            1,
        )
        assert parts_sum == b["total_score"]
        assert p["score"] == b["total_score"]


def test_approve_and_reject_match_api():
    storage_service.load_seed_resources()

    req = StoredRequest(
        id="req_approve_api_test",
        type=IncidentType.RESCUE,
        lat=26.852,
        lng=80.940,
        people_count=4,
        status=RequestStatus.NEW,
    )
    storage_service.save_request(req, actor="test")

    # Fetch proposals
    resp = client.get(f"/api/requests/{req.id}/matches", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    proposals = resp.json()
    assert len(proposals) >= 2

    top_proposal = proposals[0]
    match_id = top_proposal["match_id"]
    resource_id = top_proposal["resource_id"]
    initial_cap = top_proposal["capacity_remaining"]

    # 1. Approve match
    approve_resp = client.post(
        f"/api/matches/{match_id}/approve",
        json={"allow_overcommit": False},
        headers=AUTH_HEADERS,
    )
    assert approve_resp.status_code == 200
    approved_data = approve_resp.json()
    assert approved_data["state"] == "approved"

    # Capacity was decremented by 4
    res = storage_service.get_resource(resource_id)
    assert res.capacity_remaining == initial_cap - 4

    # 2. Reject another match
    second_proposal = proposals[1]
    second_match_id = second_proposal["match_id"]
    reject_resp = client.post(
        f"/api/matches/{second_match_id}/reject",
        json={"reason": "Resource allocated to higher urgency site"},
        headers=AUTH_HEADERS,
    )
    assert reject_resp.status_code == 200
    rejected_data = reject_resp.json()
    assert rejected_data["state"] == "rejected"
    assert "allocated" in rejected_data["rejected_reason"]


def test_list_resources_api():
    storage_service.load_seed_resources()
    resp = client.get("/api/resources", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    resources = resp.json()
    assert len(resources) >= 10
