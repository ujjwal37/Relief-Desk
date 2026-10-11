import threading

from fastapi.testclient import TestClient

from app.main import app
from app.models.firestore_models import (
    RequestStatus,
    ResourceKind,
    ResourceStatus,
    StoredRequest,
    StoredResource,
)
from app.models.schemas import HazardType, IncidentType, VulnerableFlags
from app.tools.capacity import (
    OvercommitRequired,
    apply_release,
    apply_reserve,
    capacity_service,
    load_resource_seed,
)
from app.tools.scoring import MatchWeights, match_score
from app.tools.storage import storage_service

client = TestClient(app)

RIVERBEND_BBOX = {
    "min_lat": 26.78,
    "max_lat": 26.92,
    "min_lng": 80.88,
    "max_lng": 81.01,
}


def _request(
    request_id: str,
    incident: IncidentType = IncidentType.RESCUE,
    people: int = 4,
    lat: float | None = 26.839,
    lng: float | None = 80.941,
    urgency: float = 0.0,
    hazard: HazardType = HazardType.WATER_RISING,
    vulnerable: VulnerableFlags | None = None,
) -> StoredRequest:
    req = StoredRequest(
        id=request_id,
        type=incident,
        hazard=hazard,
        people_count=people,
        lat=lat,
        lng=lng,
        urgency_score=urgency,
        vulnerable=vulnerable or VulnerableFlags(),
        place_text="Ram Ghat, Riverbend",
    )
    storage_service.save_request(req, actor="test")
    return req


def _resource(
    resource_id: str,
    kind: ResourceKind,
    remaining: int,
    total: int | None = None,
    lat: float = 26.839,
    lng: float = 80.941,
    name: str = "Test resource",
) -> StoredResource:
    resource = StoredResource(
        id=resource_id,
        kind=kind,
        name=name,
        lat=lat,
        lng=lng,
        capacity_total=total if total is not None else max(remaining, 0),
        capacity_remaining=remaining,
        status=ResourceStatus.AVAILABLE if remaining > 0 else ResourceStatus.DEPLETED,
    )
    storage_service.save_resource(resource, audit=False)
    return resource


def test_seed_covers_boats_shelters_food_and_medical():
    resources = load_resource_seed()
    kinds = {resource.kind for resource in resources}
    assert kinds == {
        ResourceKind.BOAT,
        ResourceKind.SHELTER,
        ResourceKind.FOOD,
        ResourceKind.MEDICAL,
    }
    assert sum(1 for resource in resources if resource.kind == ResourceKind.BOAT) >= 2
    assert sum(1 for resource in resources if resource.kind == ResourceKind.SHELTER) >= 2
    for resource in resources:
        assert resource.synthetic is True
        assert resource.capacity_total > 0
        assert resource.capacity_remaining == resource.capacity_total
        assert RIVERBEND_BBOX["min_lat"] <= resource.lat <= RIVERBEND_BBOX["max_lat"]
        assert RIVERBEND_BBOX["min_lng"] <= resource.lng <= RIVERBEND_BBOX["max_lng"]
        dumped = resource.model_dump(mode="json")
        assert "phone" not in dumped
        assert "address" not in dumped

    listed = client.get("/api/resources")
    assert listed.status_code == 200
    ids = {row["id"] for row in listed.json()}
    assert "res_boat_ram_ghat" in ids
    assert "res_shelter_gandhi_nagar" in ids
    assert "res_food_gandhi_market" in ids
    assert "res_medical_civil_hospital" in ids


def test_match_score_breakdown_sums_and_hard_constraints():
    req = _request("req_score_boat", people=4, urgency=80)
    boat = _resource(
        "res_score_boat",
        ResourceKind.BOAT,
        remaining=12,
        total=12,
        name="Ram Ghat Rescue Boat",
    )
    scored = match_score(req, boat)
    assert scored.eligible is True
    assert scored.distance_km == 0.0
    assert scored.overcommit_risk is False
    assert set(scored.breakdown) == {"dist", "capacity", "urgency", "vuln"}
    assert scored.breakdown == {"dist": 30.0, "capacity": 25.0, "urgency": 20.0, "vuln": 20.0}
    assert scored.score == 95.0
    assert scored.score == round(sum(scored.breakdown.values()), 1)

    distance_only = match_score(req, boat, MatchWeights(w_d=1, w_c=0, w_u=0, w_v=0))
    assert distance_only.score == 100.0

    shelter = _resource(
        "res_score_shelter",
        ResourceKind.SHELTER,
        remaining=40,
        total=40,
        name="Riverfront Shelter",
    )
    shelter_score = match_score(req, shelter)
    assert shelter_score.eligible is True
    assert shelter_score.score < scored.score

    food = _resource("res_score_food", ResourceKind.FOOD, remaining=50, total=50, name="Kitchen")
    incompatible = match_score(req, food)
    assert incompatible.eligible is False
    assert incompatible.score == 0.0
    assert incompatible.hard_constraint == "type_incompatible"

    empty = _resource("res_score_empty", ResourceKind.BOAT, remaining=0, total=8, name="Empty boat")
    no_capacity = match_score(req, empty)
    assert no_capacity.eligible is False
    assert no_capacity.hard_constraint == "no_capacity"

    far = _resource(
        "res_score_far",
        ResourceKind.BOAT,
        remaining=12,
        total=12,
        lat=26.887,
        lng=80.959,
        name="Far boat",
    )
    far_score = match_score(req, far)
    assert far_score.breakdown["dist"] < scored.breakdown["dist"]
    assert far_score.score < scored.score

    unlocated = _request("req_score_unlocated", people=4, lat=None, lng=None, urgency=80)
    unknown = match_score(unlocated, boat)
    assert unknown.distance_km is None
    assert unknown.breakdown["dist"] < scored.breakdown["dist"]

    tight = _resource(
        "res_score_tight",
        ResourceKind.BOAT,
        remaining=4,
        total=12,
        name="Small boat",
    )
    over = match_score(_request("req_score_over", people=10, urgency=80), tight)
    assert over.eligible is True
    assert over.overcommit_risk is True
    assert over.breakdown["capacity"] == 10.0


def test_vulnerability_and_urgency_change_match_parts():
    clinic = _resource(
        "res_score_clinic",
        ResourceKind.MEDICAL,
        remaining=10,
        total=10,
        name="Clinic",
    )
    plain = _request(
        "req_med_plain",
        incident=IncidentType.MEDICAL,
        people=1,
        urgency=0,
        hazard=HazardType.NONE,
    )
    needy = _request(
        "req_med_need",
        incident=IncidentType.MEDICAL,
        people=1,
        urgency=0,
        hazard=HazardType.NONE,
        vulnerable=VulnerableFlags(medical_need=True),
    )
    plain_score = match_score(plain, clinic)
    needy_score = match_score(needy, clinic)
    assert needy_score.breakdown["vuln"] > plain_score.breakdown["vuln"]

    low = _request("req_urg_low", people=2, urgency=10)
    high = _request("req_urg_high", people=2, urgency=90)
    boat = _resource("res_urg_boat", ResourceKind.BOAT, remaining=10, total=10, name="Boat")
    low_score = match_score(low, boat)
    high_score = match_score(high, boat)
    assert high_score.breakdown["urgency"] > low_score.breakdown["urgency"]

    shelter = _resource(
        "res_vuln_shelter",
        ResourceKind.SHELTER,
        remaining=30,
        total=30,
        name="Shelter",
    )
    adults = _request(
        "req_adults_shelter",
        incident=IncidentType.SHELTER,
        people=5,
        hazard=HazardType.NONE,
    )
    vulnerable = _request(
        "req_vuln_shelter",
        incident=IncidentType.SHELTER,
        people=5,
        hazard=HazardType.NONE,
        vulnerable=VulnerableFlags(child=True, elderly=True),
    )
    assert (
        match_score(vulnerable, shelter).breakdown["vuln"]
        > match_score(adults, shelter).breakdown["vuln"]
    )


def test_apply_reserve_and_release_math():
    assert apply_reserve(12, 5, override=False) == (7, False)
    assert apply_reserve(4, 4, override=False) == (0, False)
    try:
        apply_reserve(4, 10, override=False)
        raised = False
    except ValueError:
        raised = True
    assert raised is True
    assert apply_reserve(4, 10, override=True) == (-6, True)
    assert apply_release(-6, 12, 10) == 4
    assert apply_release(18, 20, 5) == 20


def test_approve_decrements_capacity_once_and_reject_releases():
    _request("req_approve_boat", people=5, urgency=70)
    _resource(
        "res_approve_boat",
        ResourceKind.BOAT,
        remaining=12,
        total=12,
        name="Approve Boat",
    )
    proposed = client.post(
        "/api/matches",
        json={
            "request_id": "req_approve_boat",
            "resource_id": "res_approve_boat",
            "actor": "coordinator_demo",
        },
    )
    assert proposed.status_code == 201
    match_id = proposed.json()["id"]
    assert proposed.json()["state"] == "proposed"
    assert storage_service.get_resource("res_approve_boat").capacity_remaining == 12

    approved = client.post(
        f"/api/matches/{match_id}/approve",
        json={"approved_by": "coordinator_demo", "override": False},
    )
    assert approved.status_code == 200
    body = approved.json()
    assert body["state"] == "approved"
    assert body["overcommit"] is False
    assert body["requires_override"] is False
    assert body["capacity_remaining"] == 7
    assert body["reserved_units"] == 5
    assert body["call_112"] == "In an emergency call 112"
    assert body["audit_action"] == "capacity_reserved"
    resource = storage_service.get_resource("res_approve_boat")
    assert resource.capacity_remaining == 7
    assert resource.status == ResourceStatus.AVAILABLE
    assert storage_service.get_request("req_approve_boat").status == RequestStatus.APPROVED

    again = client.post(
        f"/api/matches/{match_id}/approve",
        json={"approved_by": "coordinator_demo", "override": False},
    )
    assert again.status_code == 200
    assert again.json()["idempotent"] is True
    assert storage_service.get_resource("res_approve_boat").capacity_remaining == 7

    trail = storage_service.get_audit_trail(target=match_id)
    reserved = [entry for entry in trail if entry.action == "capacity_reserved"]
    assert len(reserved) == 1
    assert reserved[0].actor == "coordinator_demo"
    assert reserved[0].before["capacity_remaining"] == 12
    assert reserved[0].after["capacity_remaining"] == 7

    rejected = client.post(
        f"/api/matches/{match_id}/reject",
        json={"rejected_by": "coordinator_demo", "reason": "wrong boat for this ward"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["state"] == "rejected"
    assert rejected.json()["audit_action"] == "capacity_released"
    assert storage_service.get_resource("res_approve_boat").capacity_remaining == 12
    assert storage_service.get_request("req_approve_boat").status == RequestStatus.MATCHED
    released = [
        entry
        for entry in storage_service.get_audit_trail(target=match_id)
        if entry.action == "capacity_released"
    ]
    assert len(released) == 1
    assert released[0].after["reason"] == "wrong boat for this ward"
    assert storage_service.get_match(match_id) is not None


def test_exact_fit_depletes_without_overcommit_warning():
    _request("req_exact_fit", people=6)
    _resource("res_exact_boat", ResourceKind.BOAT, remaining=6, total=6, name="Exact Boat")
    proposed = client.post(
        "/api/matches",
        json={"request_id": "req_exact_fit", "resource_id": "res_exact_boat"},
    )
    assert proposed.status_code == 201
    assert proposed.json()["overcommit"] is False
    approved = client.post(
        f"/api/matches/{proposed.json()['id']}/approve",
        json={"approved_by": "coordinator_demo"},
    )
    assert approved.status_code == 200
    assert approved.json()["warning"] is None
    resource = storage_service.get_resource("res_exact_boat")
    assert resource.capacity_remaining == 0
    assert resource.status == ResourceStatus.DEPLETED


def test_overcommit_requires_override_and_is_audited():
    _request("req_overcommit", people=10, urgency=60)
    _resource(
        "res_overcommit_boat",
        ResourceKind.BOAT,
        remaining=4,
        total=12,
        name="Small Ram Ghat Boat",
    )
    proposed = client.post(
        "/api/matches",
        json={
            "request_id": "req_overcommit",
            "resource_id": "res_overcommit_boat",
            "actor": "coordinator_demo",
        },
    )
    assert proposed.status_code == 201
    proposal = proposed.json()
    match_id = proposal["id"]
    assert proposal["overcommit"] is True
    assert "10" in proposal["warning"]
    assert "4" in proposal["warning"]
    assert storage_service.get_resource("res_overcommit_boat").capacity_remaining == 4

    blocked = client.post(
        f"/api/matches/{match_id}/approve",
        json={"approved_by": "coordinator_demo", "override": False},
    )
    assert blocked.status_code == 409
    detail = blocked.json()["detail"]
    assert detail["requires_override"] is True
    assert detail["overcommit"] is True
    assert detail["state"] == "proposed"
    assert detail["capacity_remaining"] == 4
    assert detail["people_requested"] == 10
    assert "Overcommit warning" in detail["warning"]
    assert detail["call_112"] == "In an emergency call 112"
    assert storage_service.get_resource("res_overcommit_boat").capacity_remaining == 4
    assert storage_service.get_match(match_id).state.value == "proposed"

    warning_audit = [
        entry
        for entry in storage_service.get_audit_trail(target=match_id)
        if entry.action == "overcommit_warning"
    ]
    assert len(warning_audit) == 1
    assert warning_audit[0].actor == "coordinator_demo"
    assert warning_audit[0].after["requires_override"] is True
    assert warning_audit[0].after["override"] is False
    assert warning_audit[0].before["capacity_remaining"] == 4

    overridden = client.post(
        f"/api/matches/{match_id}/approve",
        json={"approved_by": "coordinator_demo", "override": True},
    )
    assert overridden.status_code == 200
    body = overridden.json()
    assert body["state"] == "approved"
    assert body["overcommit"] is True
    assert body["requires_override"] is False
    assert body["capacity_remaining"] == -6
    assert body["audit_action"] == "capacity_overcommit_override"
    assert "Overcommit warning" in body["warning"]
    resource = storage_service.get_resource("res_overcommit_boat")
    assert resource.capacity_remaining == -6
    assert resource.status == ResourceStatus.OVERCOMMITTED
    assert storage_service.get_request("req_overcommit").status == RequestStatus.APPROVED

    override_audit = [
        entry
        for entry in storage_service.get_audit_trail(target=match_id)
        if entry.action == "capacity_overcommit_override"
    ]
    assert len(override_audit) == 1
    assert override_audit[0].actor == "coordinator_demo"
    assert override_audit[0].after["override"] is True
    assert override_audit[0].after["overcommit"] is True
    assert override_audit[0].after["capacity_remaining"] == -6
    assert override_audit[0].before["capacity_remaining"] == 4

    released = client.post(
        f"/api/matches/{match_id}/reject",
        json={"rejected_by": "coordinator_demo", "reason": "hold for a larger boat"},
    )
    assert released.status_code == 200
    restored = storage_service.get_resource("res_overcommit_boat")
    assert restored.capacity_remaining == 4
    assert restored.status == ResourceStatus.AVAILABLE


def test_incompatible_proposal_is_rejected_and_capacity_stays():
    _request("req_food_mismatch", incident=IncidentType.RESCUE, people=3)
    _resource("res_food_mismatch", ResourceKind.FOOD, remaining=20, total=20, name="Kitchen")
    response = client.post(
        "/api/matches",
        json={"request_id": "req_food_mismatch", "resource_id": "res_food_mismatch"},
    )
    assert response.status_code == 422
    assert storage_service.get_resource("res_food_mismatch").capacity_remaining == 20


def test_concurrent_approvals_cannot_oversubscribe():
    _resource(
        "res_race_boat",
        ResourceKind.BOAT,
        remaining=5,
        total=10,
        name="Race Boat",
    )
    match_ids = []
    for index in (1, 2):
        _request(f"req_race_{index}", people=4, urgency=40)
        match = capacity_service.propose_match(
            f"req_race_{index}",
            "res_race_boat",
            actor="coordinator_demo",
        )
        match_ids.append(match.id)

    barrier = threading.Barrier(2, timeout=5)
    outcomes: list[tuple[str, int]] = []
    errors: list[str] = []

    def _approve(match_id: str) -> None:
        try:
            barrier.wait()
            decision = capacity_service.approve_match(
                match_id, approved_by="coordinator_demo", override=False
            )
            outcomes.append(("ok", decision.capacity_remaining))
        except OvercommitRequired as exc:
            outcomes.append(("blocked", exc.decision.capacity_remaining))
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=_approve, args=(match_id,)) for match_id in match_ids]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert errors == []
    assert sorted(outcome[0] for outcome in outcomes) == ["blocked", "ok"]
    assert storage_service.get_resource("res_race_boat").capacity_remaining == 1
    blocked = [item for item in outcomes if item[0] == "blocked"]
    assert blocked[0][1] == 1
