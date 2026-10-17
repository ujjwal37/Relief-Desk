from app.models.firestore_models import MatchState, RequestStatus
from app.tools.storage import storage_service
from app.agents.matching import matching_agent


def _approved_case():
    storage_service.reset() if hasattr(storage_service, "reset") else None
    for req in list(storage_service._requests.values()):
        if req.status not in (RequestStatus.DISPATCHED, RequestStatus.COMPLETED) and req.lat is not None:
            props = matching_agent.find_matches(req, top_n=3)
            for prop in props:
                res = storage_service._resources.get(prop.resource_id)
                if res is None or res.capacity_remaining < (req.people_count or 1):
                    continue
                try:
                    storage_service.approve_match(prop.match_id, approved_by="t")
                except ValueError:
                    continue
                return req, prop
    raise AssertionError("no approvable case in seed data")


def test_undo_gives_back_seats_and_returns_case_to_waiting():
    req, prop = _approved_case()
    res = storage_service._resources[prop.resource_id]
    seats_after_approve = res.capacity_remaining
    assert storage_service._requests[req.id].status == RequestStatus.DISPATCHED

    m = storage_service.undo_approval(prop.match_id, actor="t")

    assert m.state == MatchState.PROPOSED
    r = storage_service._requests[req.id]
    assert r.status == RequestStatus.MATCHED and r.assigned_resource_id is None
    res = storage_service._resources[prop.resource_id]
    assert res.capacity_remaining > seats_after_approve
    assert res.assigned_request_id != req.id and not res.simulated
    others = [x for x in storage_service._matches.values() if x.request_id == req.id and x.id != prop.match_id]
    assert all(x.state == MatchState.PROPOSED for x in others if x.rejected_reason is None)
    assert not any(x.rejected_reason == "Another team was dispatched" for x in others)
    # retry-safe, and it can be approved again
    storage_service.undo_approval(prop.match_id, actor="t")
    assert storage_service.approve_match(prop.match_id, approved_by="t").state == MatchState.APPROVED
    storage_service.undo_approval(prop.match_id, actor="t")
