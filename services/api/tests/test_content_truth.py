"""Content truth: unknown people stays unknown; a confirmed hoax closes without sending."""
from app.agents.pipeline import score_urgency
from app.tools.storage import storage_service


def test_score_urgency_accepts_unknown_people():
    result = score_urgency(None, "rescue")
    assert result is not None


def test_dismiss_hoax_closes_without_dispatch():
    rows = [r for r in storage_service._requests.values() if r.status.value == "new"]
    if not rows:
        return
    req = rows[0]
    out = storage_service.dismiss_hoax(req.id, actor="test")
    assert out.status.value == "closed"
    assert "dismissed_hoax" in out.flags
    assert out.assigned_resource_id is None

def test_demo_has_hoax_case_and_unknown_people():
    from app.tools.demo_cases import DEMO_CASES
    hoax = [r for r in DEMO_CASES if r.get("hoax_reason")]
    assert hoax and hoax[0]["people"] is None
    road = [r for r in DEMO_CASES if r["id"] == "DEMO-106"][0]
    assert road["people"] is None


def test_no_team_options_all_busy_offers_reserve():
    from app.agents.no_team import no_team_options
    from app.models.firestore_models import ResourceStatus
    reqs = [r for r in storage_service._requests.values() if r.type.value == "rescue" and r.lat is not None]
    res = storage_service.list_resources()
    if not reqs or not res:
        return
    boats = [r.model_copy() for r in res if r.kind.value == "boat"]
    for b in boats:
        b.status = ResourceStatus.DISPATCHED
    out = no_team_options(reqs[0], boats)
    assert out["reason"] == "all_busy"
    assert out["options"]["reserve"] is not None
    assert out["options"]["escalate"]["available"] is True
