"""The dispatch record is written once at Approve and does not follow later matching (judge r6, item 2)."""
from app.agents.matching import matching_agent
from app.tools.storage import storage_service


def test_dispatch_record_is_frozen_at_approve():
    storage_service.load_full_scenario()
    req = next(r for r in storage_service._requests.values() if r.id == "INC-001")
    best = matching_agent.find_matches(req, save_to_storage=True)[0]
    storage_service.approve_match(getattr(best, "match_id", None) or best.id, approved_by="test")
    sent = storage_service.get_request("INC-001")
    frozen = dict(sent.dispatch)
    assert frozen["resource_name"] and frozen["distance_km"] is not None and frozen["seats"] is not None
    matching_agent.find_matches(sent, save_to_storage=True)
    assert storage_service.get_request("INC-001").dispatch == frozen
