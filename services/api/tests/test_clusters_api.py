from fastapi.testclient import TestClient
from app.main import app
from app.models.firestore_models import StoredRequest, RequestStatus
from app.models.schemas import IncidentType, HazardType
from app.tools.storage import storage_service

client = TestClient(app)


def test_merge_split_undo_api_and_audit():
    # Setup two test requests in storage
    r1 = StoredRequest(
        id="req_m1",
        type=IncidentType.RESCUE,
        place_text="Sangam Primary School",
        people_count=4,
        hazard=HazardType.WATER_RISING,
        status=RequestStatus.NEW
    )
    r2 = StoredRequest(
        id="req_m2",
        type=IncidentType.RESCUE,
        place_text="Near Sangam School",
        people_count=3,
        hazard=HazardType.WATER_RISING,
        status=RequestStatus.NEW
    )
    storage_service.save_request(r1, actor="test")
    storage_service.save_request(r2, actor="test")

    # 1. Merge requests via POST /api/requests/req_m1/merge
    merge_payload = {
        "secondary_request_id": "req_m2",
        "evidence": ["Both reports within 50m of Sangam School", "Identical water_rising hazard"],
        "merged_by": "coordinator_jane"
    }
    merge_resp = client.post("/api/requests/req_m1/merge", json=merge_payload)
    assert merge_resp.status_code == 200
    merge_data = merge_resp.json()
    cluster_id = merge_data["cluster_id"]
    assert cluster_id.startswith("clust_")
    assert merge_data["primary_request_id"] == "req_m1"
    assert merge_data["secondary_request_id"] == "req_m2"

    # Verify both requests now reference cluster_id
    assert storage_service.get_request("req_m1").cluster_id == cluster_id
    assert storage_service.get_request("req_m2").cluster_id == cluster_id

    # 2. Get evidence card data via GET /api/clusters/{cluster_id}
    evidence_resp = client.get(f"/api/clusters/{cluster_id}")
    assert evidence_resp.status_code == 200
    ev_data = evidence_resp.json()
    assert len(ev_data["evidence"]) == 2
    assert ev_data["undone"] is False

    # 3. Split / undo merge via POST /api/requests/req_m1/split
    split_resp = client.post(f"/api/requests/req_m1/split?actor=coordinator_jane")
    assert split_resp.status_code == 200
    split_data = split_resp.json()
    assert split_data["undone"] is True
    assert set(split_data["restored_request_ids"]) == {"req_m1", "req_m2"}

    # 4. Acceptance criteria verification: Split restores both requests
    r1_restored = storage_service.get_request("req_m1")
    r2_restored = storage_service.get_request("req_m2")
    assert r1_restored.cluster_id is None
    assert r2_restored.cluster_id is None

    # 5. Acceptance criteria verification: Audited
    cluster_audit = storage_service.get_audit_trail(target=cluster_id)
    actions = [a.action for a in cluster_audit]
    assert "cluster_created" in actions
    assert "cluster_split" in actions
    assert any(a.actor == "coordinator_jane" for a in cluster_audit)
