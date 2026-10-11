"""The assist dispatcher holds a team and waits for a person before dispatch."""
import threading

from google.adk.agents import LlmAgent

from app.agents.dispatcher import (
    DISPATCHER,
    check_capacity,
    commit_dispatch,
    find_teams,
    list_open_cases,
    propose_assignment,
    reset_calls,
    reserve_hold,
)
from app.models.firestore_models import IncidentType, RequestStatus, ResourceKind, ResourceStatus, StoredRequest, StoredResource
from app.tools.storage import storage_service


def _case(case_id: str, people: int) -> StoredRequest:
    req = StoredRequest(
        id=case_id,
        type=IncidentType.RESCUE,
        people_count=people,
        place_text="Synthetic jetty",
        lat=9.45,
        lng=76.39,
        status=RequestStatus.NEW,
    )
    return storage_service.save_request(req, actor="test")


def _boat(resource_id: str, seats: int) -> StoredResource:
    res = StoredResource(
        id=resource_id,
        kind=ResourceKind.BOAT,
        name=resource_id,
        ward_id="ward_2",
        lat=9.45,
        lng=76.39,
        capacity_total=seats,
        capacity_remaining=seats,
        status=ResourceStatus.AVAILABLE,
    )
    return storage_service.save_resource(res, actor="test")


def test_tool_order_and_commit_waits_for_confirmation():
    assert isinstance(DISPATCHER, LlmAgent)
    names = [tool.name for tool in DISPATCHER.tools]
    assert names == [
        "list_open_cases",
        "find_teams",
        "check_capacity",
        "propose_assignment",
        "reserve_hold",
        "commit_dispatch",
    ]
    assert DISPATCHER.tools[-1]._require_confirmation is True
    reset_calls()
    _case("req_assist_a", 2)
    _boat("boat_assist_a", 6)
    assert list_open_cases()
    assert find_teams("boat")
    assert check_capacity("boat_assist_a")["free"] == 6
    proposal = propose_assignment("req_assist_a", "boat_assist_a")
    assert proposal["dispatched"] is False
    stored = storage_service.get_request("req_assist_a")
    assert stored.status == RequestStatus.NEW
    blocked = commit_dispatch("req_assist_a", "boat_assist_a", confirmed=False)
    assert blocked["dispatched"] is False
    assert blocked["needs_confirmation"] is True
    assert storage_service.get_request("req_assist_a").status == RequestStatus.NEW
    assert calls_so_far() == [
        "list_open_cases",
        "find_teams",
        "check_capacity",
        "propose_assignment",
        "commit_dispatch",
    ]


def calls_so_far():
    from app.agents.dispatcher import calls
    return calls()


def test_reject_releases_the_hold_and_audits_it():
    _case("req_assist_b", 3)
    _boat("boat_assist_b", 5)
    proposal = propose_assignment("req_assist_b", "boat_assist_b")
    assert storage_service.get_resource("boat_assist_b").capacity_remaining == 2
    match = storage_service.get_match(proposal["match_id"])
    storage_service.reject_match(match.id, reason="wrong team", actor="coordinator")
    restored = storage_service.get_resource("boat_assist_b")
    assert restored.capacity_remaining == 5
    assert restored.hold_request_id is None
    assert storage_service.get_request("req_assist_b").status == RequestStatus.NEW
    trail = storage_service.get_audit_trail(target="boat_assist_b")
    assert any(entry.action == "capacity_reserved" for entry in trail)
    assert any(entry.action == "capacity_released" for entry in trail)
    rejected = storage_service.get_audit_trail(target=match.id)
    assert any(entry.action == "match_rejected" for entry in rejected)


def test_shortage_is_explained_and_two_coordinators_do_not_share_one_boat():
    _case("req_assist_c1", 4)
    _case("req_assist_c2", 4)
    _boat("boat_assist_one", 4)
    first = {}
    second = {}

    def claim(case_id, box):
        box["result"] = propose_assignment(case_id, "boat_assist_one")

    left = threading.Thread(target=claim, args=("req_assist_c1", first))
    right = threading.Thread(target=claim, args=("req_assist_c2", second))
    left.start()
    right.start()
    left.join()
    right.join()
    results = [first["result"], second["result"]]
    assert sum(1 for item in results if item.get("ok")) == 1
    denied = next(item for item in results if not item.get("ok"))
    assert "Not enough teams" in denied["explanation"]
    assert denied["dispatched"] is False
    assert storage_service.get_request("req_assist_c1").status == RequestStatus.NEW
    assert storage_service.get_request("req_assist_c2").status == RequestStatus.NEW
    # The unused reserve_hold tool also reports a shortage instead of dispatching.
    again = reserve_hold("req_assist_c2", "boat_assist_one", 4)
    assert again["held"] is False
    assert "shortage" in again["explanation"]
