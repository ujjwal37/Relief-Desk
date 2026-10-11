"""Nearby teams are offered first. A far team keeps its real straight-line ETA."""
from app.agents.matching import matching_agent
from app.models.firestore_models import ResourceKind, StoredRequest
from app.models.schemas import IncidentType, VulnerableFlags
from app.tools.storage import storage_service


def _eta(km: float) -> int:
    return max(1, round((km / 20.0) * 60))


def test_oxygen_case_matches_the_varapuzha_clinic():
    storage_service.load_seed_resources()
    req = StoredRequest(
        id="req_oxygen_varapuzha",
        type=IncidentType.MEDICAL,
        lat=10.07985,
        lng=76.27371,
        people_count=3,
        urgency_score=90.0,
        vulnerable=VulnerableFlags(medical_need=True),
    )
    proposals = matching_agent.find_matches(req, top_n=5, save_to_storage=False)
    assert proposals
    best = proposals[0]
    assert best.resource_id == "RES-MED-04"
    assert best.resource_kind == ResourceKind.MEDICAL
    assert best.breakdown.distance_km < 2
    assert best.eta_minutes == _eta(best.breakdown.distance_km)
    assert best.eta_minutes < 15
    assert all(p.breakdown.distance_km <= 40 for p in proposals)


def test_alappuzha_rescue_does_not_offer_the_wayanad_boat():
    storage_service.load_seed_resources()
    req = StoredRequest(
        id="req_alappuzha_rescue",
        type=IncidentType.RESCUE,
        lat=9.436,
        lng=76.398,
        people_count=4,
        urgency_score=80.0,
    )
    proposals = matching_agent.find_matches(req, top_n=5, save_to_storage=False)
    assert proposals
    assert all(p.resource_id != "RES-BOAT-04" for p in proposals)
    assert proposals[0].breakdown.distance_km < 5
    assert proposals[0].eta_minutes == _eta(proposals[0].breakdown.distance_km)
    assert proposals[0].eta_minutes < 20


def test_distant_case_shows_the_real_wait():
    storage_service.load_seed_resources()
    req = StoredRequest(
        id="req_chalakudy_rescue",
        type=IncidentType.RESCUE,
        lat=10.303,
        lng=76.335,
        people_count=2,
        urgency_score=70.0,
    )
    proposals = matching_agent.find_matches(req, top_n=5, save_to_storage=False)
    assert proposals
    best = proposals[0]
    assert best.resource_id != "RES-BOAT-04"
    assert best.breakdown.distance_km > 40
    assert best.eta_minutes == _eta(best.breakdown.distance_km)
    assert best.eta_minutes > 60
    assert all(p.eta_minutes < 400 for p in proposals)
