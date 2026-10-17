"""Judge r6 items 4-5: clean reporter summary, one score, no stale/far raft, data sweep."""
import pathlib

import yaml

from app.agents.chat_intake import _slot_summary
from app.agents.no_team import no_team_options
from app.agents.summary import short_faithful_summary
from app.models.firestore_models import IncidentType, ResourceKind, ResourceStatus, StoredRequest, StoredResource
from app.tools.demo_cases import DEMO_CASES

ROOT = pathlib.Path(__file__).resolve().parents[3]


def test_reporter_summary_is_one_clean_line_not_the_stitched_input():
    raw = (
        "Gandhi school ke paas ghar mein paani aa gaya.\n"
        "Ab 5 log hain, 1 bachcha aur dadi bimaar.\n"
        "Please jaldi boat bhejo chat par paani aa raha hai."
    )
    summary = short_faithful_summary(raw)
    assert "\n" not in summary
    assert "Please jaldi" not in summary
    line = _slot_summary(IncidentType.RESCUE, 5, "Gandhi School", "en")
    assert "\n" not in line and "5" in line and "Gandhi School" in line


def _res(rid, lat, updated):
    return StoredResource(
        id=rid, name=rid, kind=ResourceKind.BOAT, status=ResourceStatus.AVAILABLE, ward_id="ward_1",
        capacity_total=10, capacity_remaining=10, lat=lat, lng=76.427, location_updated_at=updated,
    )


def test_stale_or_far_raft_is_never_offered_as_the_wider_search():
    req = StoredRequest(id="req_noteam", type=IncidentType.RESCUE, people_count=4, lat=9.455, lng=76.427)
    stale = _res("raft_stale_91km", 10.27, "2020-01-01T00:00:00Z")
    far = _res("boat_far_33km", 9.75, "2026-10-17T12:00:00Z")
    opts = no_team_options(req, [stale, far])
    assert opts["options"]["wider"] is None
    assert opts["options"]["escalate"] is not None


def test_data_sweep():
    thotta = next(c for c in DEMO_CASES if "Thottappally" in (c.get("place") or ""))
    assert "south of Kuttanad" not in thotta["place"]
    seeds = yaml.safe_load((ROOT / "data" / "synthetic" / "flood_v1" / "seeds.yaml").read_text(encoding="utf-8"))
    text = yaml.safe_dump(seeds, allow_unicode=True)
    assert "Mata Mandir" not in text
    assert "bridge bridge" not in text.lower()
    inc = {i["id"]: i for i in seeds["incidents"]}
    assert inc["INC-011"]["landmark_id"] == "LM-09"
