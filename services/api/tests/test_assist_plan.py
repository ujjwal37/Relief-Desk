"""Assist planning holds teams inside one coordinator's wards and does not dispatch."""
from app.api.assist import plan_for, shortages_for
from app.api.auth import create_coordinator_token, verify_coordinator_token
from app.models.firestore_models import RequestStatus
from app.tools.storage import storage_service


def test_two_coordinators_get_disjoint_holds_and_nothing_is_dispatched():
    south = verify_coordinator_token(create_coordinator_token("south-coordinator@reliefdesk.internal"))
    north = verify_coordinator_token(create_coordinator_token("north-coordinator@reliefdesk.internal"))
    before = {req.id: req.status for req in storage_service.list_requests()}
    south_body = plan_for(south.email)
    north_body = plan_for(north.email)
    try:
        south_ids = {row["resource_id"] for row in south_body["proposals"] if not row["expired"]}
        north_ids = {row["resource_id"] for row in north_body["proposals"] if not row["expired"]}
        assert south_ids.isdisjoint(north_ids)
        assert south_body["proposals"]
        for row in south_body["proposals"] + north_body["proposals"]:
            assert row["dispatched"] is False
            req = storage_service.get_request(row["request_id"])
            assert req is not None
            assert req.status not in (RequestStatus.DISPATCHED, RequestStatus.APPROVED)
            if not row["expired"]:
                assert row["expires_at"]
        assert shortages_for(south.email) == south_body["shortages"]
        assert shortages_for(north.email) == north_body["shortages"]
        for item in south_body["shortages"] + north_body["shortages"]:
            assert item["need"] > item["have"]
            assert "Not enough teams" in item["explanation"]
        for req in storage_service.list_requests():
            if req.id in before and before[req.id] == RequestStatus.NEW:
                assert req.status == RequestStatus.NEW
    finally:
        for row in south_body["proposals"] + north_body["proposals"]:
            match = storage_service.get_match(row["match_id"])
            if match is not None and match.state.value == "proposed":
                storage_service.reject_match(match.id, reason="test release", actor="test")
