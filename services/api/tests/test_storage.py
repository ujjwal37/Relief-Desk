from app.tools.storage import StorageService
from app.models.firestore_models import StoredRequest, RequestStatus
from app.models.schemas import IncidentType, HazardType


def test_report_stored_raw_immediately():
    storage = StorageService()
    raw = "Riverbend Gandhi school ke paas 4 log chat par hain"
    report = storage.save_report_raw(
        raw_text=raw,
        channel="text",
        lang="hinglish",
        source_id="device_anon_99",
        trust_level="anonymous"
    )

    assert report.id.startswith("rep_")
    assert report.raw_text == raw
    assert report.channel == "text"
    assert report.trust_level == "anonymous"

    # Verify audit entry generated for raw report creation
    trail = storage.get_audit_trail(target=report.id)
    assert len(trail) >= 1
    assert trail[0].action == "report_stored_raw"
    assert trail[0].target == report.id


def test_audit_entry_on_every_state_change():
    storage = StorageService()
    req = StoredRequest(
        id="req_test_01",
        type=IncidentType.RESCUE,
        place_text="Sangam Vihar",
        hazard=HazardType.WATER_RISING,
        people_count=4,
        status=RequestStatus.NEW
    )
    storage.save_request(req, actor="intake_worker")

    # Change status to MATCHED
    storage.update_request_status("req_test_01", RequestStatus.MATCHED, actor="matching_engine")

    # Change status to APPROVED
    storage.update_request_status("req_test_01", RequestStatus.APPROVED, actor="coordinator_bob")

    trail = storage.get_audit_trail(target="req_test_01")
    assert len(trail) == 3
    assert trail[0].action == "request_created"
    assert trail[1].action == "status_change"
    assert trail[1].before["status"] == "new"
    assert trail[1].after["status"] == "matched"
    assert trail[1].actor == "matching_engine"

    assert trail[2].action == "status_change"
    assert trail[2].before["status"] == "matched"
    assert trail[2].after["status"] == "approved"
    assert trail[2].actor == "coordinator_bob"


def test_cluster_create_and_split_is_audited():
    storage = StorageService()
    cluster = storage.create_cluster(
        request_ids=["req_1", "req_2"],
        evidence=["same ward 2 landmark", "posted within 5 mins"],
        merged_by="dedupe_agent"
    )
    assert cluster.undone is False

    trail = storage.get_audit_trail(target=cluster.id)
    assert len(trail) == 1
    assert trail[0].action == "cluster_created"

    # Split the cluster
    split_cluster = storage.split_cluster(cluster.id, actor="coordinator_alice")
    assert split_cluster.undone is True

    trail2 = storage.get_audit_trail(target=cluster.id)
    assert len(trail2) == 2
    assert trail2[1].action == "cluster_split"
    assert trail2[1].actor == "coordinator_alice"
