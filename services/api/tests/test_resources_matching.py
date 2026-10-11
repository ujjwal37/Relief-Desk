import pytest
from app.models.firestore_models import (
    StoredRequest,
    StoredResource,
    ResourceKind,
    ResourceStatus,
    RequestStatus,
    StoredMatch,
    MatchState,
)
from app.models.schemas import IncidentType, HazardType, VulnerableFlags
from app.tools.storage import storage_service
from app.tools.scoring import scoring_engine


def test_seed_resources_loaded():
    count = storage_service.load_seed_resources()
    assert count >= 10
    boats = storage_service.list_resources(kind=ResourceKind.BOAT)
    assert len(boats) >= 3
    shelters = storage_service.list_resources(kind=ResourceKind.SHELTER)
    assert len(shelters) >= 2


def test_match_score_breakdown_and_hard_constraints():
    storage_service.load_seed_resources()

    # Request: 8 people stranded, flood rescue, child + elderly
    req = StoredRequest(
        id="req_rescue_test",
        type=IncidentType.RESCUE,
        lat=26.853,
        lng=80.940,
        people_count=8,
        hazard=HazardType.WATER_RISING,
        urgency_score=90.0,
        vulnerable=VulnerableFlags(child=True, elderly=True),
    )

    # Compatible boat nearby
    boat = storage_service.get_resource("RES-BOAT-01")
    assert boat is not None
    breakdown = scoring_engine.compute_match_score(req, boat)
    assert breakdown is not None

    # Check that parts sum to total_score
    parts_sum = round(
        breakdown.distance_score
        + breakdown.capacity_fit_score
        + breakdown.urgency_score
        + breakdown.vulnerability_fit_score,
        1,
    )
    assert parts_sum == breakdown.total_score
    assert breakdown.total_score >= 80.0  # high match score

    # Hard constraint 1: Medical unit is incompatible with pure flood rescue
    med = storage_service.get_resource("RES-MED-01")
    assert med is not None
    assert scoring_engine.compute_match_score(req, med) is None

    # Hard constraint 2: Zero capacity returns None
    depleted_boat = StoredResource(
        id="res_depleted",
        kind=ResourceKind.BOAT,
        name="Depleted Boat",
        ward_id="ward_3",
        lat=26.852,
        lng=80.941,
        capacity_total=10,
        capacity_remaining=0,
        status=ResourceStatus.DEPLETED,
    )
    assert scoring_engine.compute_match_score(req, depleted_boat) is None


def test_capacity_reserve_release_and_overcommit():
    res = StoredResource(
        id="res_test_cap",
        kind=ResourceKind.BOAT,
        name="Test Patrol Boat",
        ward_id="ward_1",
        lat=26.845,
        lng=80.932,
        capacity_total=10,
        capacity_remaining=10,
    )
    storage_service.save_resource(res, actor="test")

    # Reserve 6 capacity
    updated_res, is_overcommit = storage_service.reserve_capacity(
        resource_id="res_test_cap", amount=6, actor="coordinator_test"
    )
    assert updated_res.capacity_remaining == 4
    assert is_overcommit is False

    # Overcommit warning: trying to reserve 8 when only 4 remain
    with pytest.raises(ValueError) as excinfo:
        storage_service.reserve_capacity(
            resource_id="res_test_cap", amount=8, allow_overcommit=False
        )
    assert "Overcommit warning" in str(excinfo.value)

    # Override overcommit with explicit flag
    updated_res_ov, is_overcommit2 = storage_service.reserve_capacity(
        resource_id="res_test_cap",
        amount=8,
        allow_overcommit=True,
        actor="coordinator_test",
    )
    assert is_overcommit2 is True
    assert updated_res_ov.capacity_remaining == 0
    assert updated_res_ov.status == ResourceStatus.DEPLETED

    # Check audit log records capacity_reserved with overcommit details
    audit = storage_service.get_audit_trail(target="res_test_cap")
    actions = [a.action for a in audit]
    assert "capacity_reserved" in actions
    overcommit_audit = [a for a in audit if a.after and a.after.get("overcommit") is True]
    assert len(overcommit_audit) == 1
    assert overcommit_audit[0].after.get("overcommit_override") is True


def test_approve_match_capacity_transaction():
    storage_service.load_seed_resources()

    req = StoredRequest(
        id="req_match_tx",
        type=IncidentType.RESCUE,
        lat=26.852,
        lng=80.941,
        people_count=4,
        status=RequestStatus.NEW,
    )
    storage_service.save_request(req, actor="test")

    boat = storage_service.get_resource("RES-BOAT-02")
    assert boat is not None
    initial_cap = boat.capacity_remaining

    breakdown = scoring_engine.compute_match_score(req, boat)
    assert breakdown is not None

    match = StoredMatch(
        id="match_test_01",
        request_id="req_match_tx",
        resource_id=boat.id,
        score=breakdown.total_score,
        breakdown=breakdown,
        state=MatchState.PROPOSED,
    )
    storage_service.save_match(match, actor="test")

    # Approve match
    approved = storage_service.approve_match(
        match_id="match_test_01", approved_by="coordinator_lead"
    )
    assert approved.state == MatchState.APPROVED
    assert approved.approved_by == "coordinator_lead"

    # Verify resource capacity was decremented by 4
    updated_boat = storage_service.get_resource("RES-BOAT-02")
    assert updated_boat.capacity_remaining == initial_cap - 4

    # Verify request status transitioned to APPROVED
    updated_req = storage_service.get_request("req_match_tx")
    assert updated_req.status == RequestStatus.APPROVED
