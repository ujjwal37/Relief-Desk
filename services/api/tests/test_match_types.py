"""Rescue goes to a boat. Busy boats are not replaced with a shelter."""
from app.agents.matching import matching_agent
from app.models.firestore_models import ResourceKind, ResourceStatus
from app.models.schemas import HazardType, IncidentType, VulnerableFlags
from app.models.firestore_models import StoredRequest
from app.tools.storage import storage_service


def _rescue(req_id: str) -> StoredRequest:
    return StoredRequest(
        id=req_id,
        type=IncidentType.RESCUE,
        lat=9.436,
        lng=76.398,
        people_count=4,
        hazard=HazardType.WATER_RISING,
        urgency_score=90.0,
        vulnerable=VulnerableFlags(child=True),
    )


def test_rescue_matches_a_boat_not_a_shelter():
    storage_service.load_seed_resources()
    proposals = matching_agent.find_matches(_rescue("req_type_boat"), top_n=5, save_to_storage=False)
    assert proposals
    assert proposals[0].resource_kind == ResourceKind.BOAT
    assert proposals[0].is_fallback is False
    assert all(p.resource_kind == ResourceKind.BOAT for p in proposals)
    assert all(not p.is_fallback for p in proposals)


def test_rescue_offers_nothing_when_boats_are_busy():
    storage_service.load_seed_resources()
    try:
        for boat in storage_service.list_resources(kind=ResourceKind.BOAT):
            boat.status = ResourceStatus.BUSY
        req = _rescue("req_type_fallback")
        req.lat = 9.436
        req.lng = 76.398
        proposals = matching_agent.find_matches(req, top_n=3, save_to_storage=False)
        assert proposals == []
    finally:
        storage_service.load_seed_resources()
