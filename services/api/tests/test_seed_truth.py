"""Every seeded card must say what its own report text says: people, children, elderly, place."""
import re

import pytest

from app.tools.storage import DESK_AREA_KM, DESK_CENTER, in_desk_area, storage_service

PEOPLE_NOUN = r"(?:people|persons|person|residents|evacuees|refugees|victims|workers|boatmen|shopkeepers|operators|volunteers|log|लोग|लोगों|പേർ|per)"
NUMBER = re.compile(rf"(?:about\s+|family of\s+)?(\d+)\s+(?:[\w-]+\s+){{0,3}}?{PEOPLE_NOUN}\b|family of (\d+)", re.I)
CHILD = re.compile(r"child|children|son\b|daughter|baby|\d+-year-old|\d+yo|kid", re.I)
ELDER = re.compile(r"elderly|grandmother|grandfather|old (?:man|woman|couple)|ammachi|അമ്മൂമ്മ", re.I)


def _seeded(mode):
    storage_service._reload_seed(mode)
    return list(storage_service._requests.values())


def _text(req):
    return " ".join(x for x in (req.raw_text, req.ai_translation, req.summary) if x)


@pytest.mark.parametrize("mode", ["small", "full"])
def test_people_count_matches_report_text(mode):
    bad = []
    for req in _seeded(mode):
        if "hoax" in (req.flags or []):
            continue
        english = " ".join(x for x in (req.ai_translation, req.summary, req.raw_text) if x)
        nums = {int(a or b) for a, b in NUMBER.findall(english)}
        if nums and req.people_count not in nums:
            bad.append((req.id, req.people_count, sorted(nums)))
        if not nums and req.people_count not in (None, 1):
            bad.append((req.id, req.people_count, "no count in text"))
    assert not bad, bad


@pytest.mark.parametrize("mode", ["small", "full"])
def test_children_and_elderly_flags_match_text(mode):
    bad = []
    for req in _seeded(mode):
        text = _text(req)
        v = req.vulnerable
        if v is None:
            continue
        if bool(v.child) != bool(CHILD.search(text)):
            bad.append((req.id, "child", v.child))
        if v.elderly and not ELDER.search(text):
            bad.append((req.id, "elderly", v.elderly))
    assert not bad, bad


def test_hero_says_eight_people_with_three_children_and_two_elderly():
    hero = next(r for r in _seeded("full") if r.id == "INC-001")
    assert hero.people_count == 8
    assert hero.vulnerable.child and hero.vulnerable.elderly
    assert "8" in hero.raw_text and "3" in hero.raw_text


@pytest.mark.parametrize("mode", ["small", "full"])
def test_every_seeded_case_is_inside_the_kuttanad_desk(mode):
    rows = _seeded(mode)
    outside = [r.id for r in rows if not in_desk_area(r.lat, r.lng)]
    assert not outside, outside
    names = " ".join(f"{r.place_text} {r.raw_text}" for r in rows)
    for place in ("Mala", "Kalpetta", "Kothamangalam", "Vythiri", "Meppadi", "Anthikad", "Varapuzha", "Chalakudy", "Aluva"):
        assert place not in names, place
    teams = " ".join(t.name for t in storage_service._resources.values())
    assert "Cedar" not in teams and "(synthetic)" not in teams


def test_full_desk_is_a_readable_queue_and_keeps_the_demo_cases():
    rows = _seeded("full")
    ids = {r.id for r in rows}
    open_rows = [r for r in rows if getattr(r.status, "value", r.status) not in ("completed", "dispatched")]
    assert 12 <= len(open_rows) <= 16
    for must in ("INC-001", "DEMO-101", "DEMO-107", "DEMO-108", "DEMO-109"):
        assert must in ids
    assert len(storage_service.get_request("DEMO-101").report_ids) == 3


def test_area_guard_drops_far_points():
    assert in_desk_area(9.436, 76.398)
    assert not in_desk_area(10.236, 76.270)  # Mala, Thrissur
    assert not in_desk_area(11.614, 76.082)  # Kalpetta, Wayanad
    assert DESK_AREA_KM == 15.0 and DESK_CENTER


@pytest.mark.parametrize("mode", ["small", "full"])
def test_seeded_life_threats_are_in_the_lane(mode):
    from app.tools.case_queue import is_life_threat, life_phrase

    rows = _seeded(mode)
    for req in rows:
        status = getattr(req.status, "value", req.status)
        if status in ("completed", "dispatched"):
            continue
        if life_phrase(req.raw_text) or life_phrase(req.ai_translation):
            assert is_life_threat(req), req.id
    by = {r.id: r for r in rows}
    assert by["DEMO-108"].ai_queue.life_phrase == "not breathing"
    assert by["DEMO-109"].ai_queue.life_phrase == "ശ്വസിക്കുന്നില്ല"
    assert by["DEMO-108"].ai_queue.life_pick == "boat"
