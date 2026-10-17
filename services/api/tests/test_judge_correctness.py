"""Judge and live-Gemini correctness. Rules path only: no Gemini key required."""
import re
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from app.agents.dedupe import MIN_MERGE_SIMILARITY, dedupe_agent
from app.agents.depth import depth_from_text, validate_depth
from app.agents.explainer import explainer_agent
from app.agents.intake import intake_agent
from app.agents.matching import eta_for_distance, matching_agent
from app.agents.no_team import no_team_options
from app.main import app
from app.models.firestore_models import MatchBreakdown, StoredRequest
from app.models.schemas import DedupeDecisionType, HazardType, IncidentType
from app.tools.gazetteer import gazetteer
from app.tools.nlu_rules import extract_place, people_count
from app.tools.storage import storage_service

client = TestClient(app)
AUTH = {"Authorization": "Bearer demo-coordinator-token"}
ROOT = Path(__file__).resolve().parents[3]
KAINAKARY = {"lat": 9.47185, "lng": 76.39571}
NEDUMUDI = {"lat": 9.436, "lng": 76.398}


def _post(text: str, pin: dict, key: str):
    response = client.post(
        "/api/reports",
        json={
            "text": text,
            "raw_text": text,
            "lang": "en",
            "channel": "text",
            "location_pin": pin,
            "idempotency_key": key,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _cards(token: str) -> list:
    listed = client.get("/api/requests", headers=AUTH)
    assert listed.status_code == 200
    needle = token.lower()
    return [
        row for row in listed.json()
        if needle in (row.get("place_text") or "").lower()
        or needle in (row.get("raw_text") or "").lower()
        or needle in (row.get("summary") or "").lower()
    ]


def test_auto_merge_similarity_floor_is_0_60():
    assert MIN_MERGE_SIMILARITY == 0.60


def test_hindi_nedumudi_four_people_does_not_merge_into_the_eight_person_hero():
    """Live Gemini: a Hindi Nedumudi report (4, pregnant) merged into RD-5422 (8) at sim 0.36."""
    hero = StoredRequest(
        id="req_hero_5422",
        type=IncidentType.RESCUE,
        place_text="Nedumudi Boat Jetty",
        raw_text="8 people trapped on the terrace near Nedumudi Boat Jetty, send a boat",
        ward_id="ward_3",
        lat=NEDUMUDI["lat"],
        lng=NEDUMUDI["lng"],
        people_count=8,
        public_code="RD-5422",
    )
    text = "नेदुमुडी बोट जेट्टी पर 4 लोग फंसे हैं, एक महिला गर्भवती है, नाव भेजो"
    extracted = intake_agent.parse_report(text)
    assert extracted.people.count == 4
    decision = dedupe_agent.evaluate(
        text, extracted, [hero], new_lat=NEDUMUDI["lat"], new_lng=NEDUMUDI["lng"], judge=False
    )
    assert decision.decision != DedupeDecisionType.DUPLICATE
    assert (decision.similarity or 0) < MIN_MERGE_SIMILARITY or decision.review or "Counts differ" in " ".join(decision.evidence)


def test_pulinkunnu_does_not_merge_into_kainakary_when_counts_and_places_differ():
    """Live Gemini: Pulinkunnu merged into a Kainakary case at sim 0.14, 2 vs 6."""
    existing = StoredRequest(
        id="req_kainakary_6",
        type=IncidentType.RESCUE,
        place_text="Kainakary Boat Jetty",
        raw_text="6 people stranded at Kainakary Boat Jetty, send a boat",
        ward_id="ward_1",
        lat=KAINAKARY["lat"],
        lng=KAINAKARY["lng"],
        people_count=6,
    )
    text = "Pulinkunnu jetty par 2 log fase hain, boat bhejo"
    extracted = intake_agent.parse_report(text)
    assert extracted.people.count == 2
    decision = dedupe_agent.evaluate(
        text, extracted, [existing], new_lat=9.45, new_lng=76.43, judge=False
    )
    assert decision.decision != DedupeDecisionType.DUPLICATE
    assert (decision.similarity is None) or decision.similarity < MIN_MERGE_SIMILARITY or decision.review is False


def test_malayalam_script_repeat_of_kainakary_jetty_is_flagged_not_merged_and_keeps_max_urgency():
    token = f"jetty{uuid.uuid4().hex[:6]}"
    english = f"6 people stranded at Kainakary Boat Jetty, send a boat {token}"
    malayalam = f"കൈനകരി ബോട്ട് ജെട്ടിയിൽ 6 പേർ കുടുങ്ങി, ബോട്ട് വേണം {token}"
    first = _post(english, KAINAKARY, f"ml-{token}-en")
    second = _post(malayalam, KAINAKARY, f"ml-{token}-ml")
    assert first["dedupe_decision"] == "new"
    assert second["dedupe_decision"] == "duplicate"
    cards = _cards(token)
    assert len(cards) == 2
    assert all(not c.get("merged_into") for c in cards)
    ml = next(c for c in cards if c["id"] == second["request_id"]) if "request_id" in second else next(c for c in cards if (c.get("possible_duplicate") or {}).get("target_id"))
    en = next(c for c in cards if c["id"] != ml["id"])
    assert ml["possible_duplicate"]["target_id"] == en["id"]
    assert all(c["people_count"] == 6 for c in cards)
    assert ml["urgency_score"] >= en["urgency_score"] - 5

    from app.tools.case_merge import fold_case

    low = StoredRequest(
        id=f"urg_low_{token}", type=IncidentType.RESCUE, place_text="Kainakary Boat Jetty",
        people_count=6, urgency_score=72, urgency_reason="Urgent 72", raw_text=malayalam, summary="Malayalam jetty report",
    )
    high = StoredRequest(
        id=f"urg_high_{token}", type=IncidentType.RESCUE, place_text="Kainakary Boat Jetty",
        people_count=6, urgency_score=90, urgency_reason="child not breathing", raw_text=english, summary="English jetty report",
    )
    storage_service.save_request(low)
    storage_service.save_request(high)
    merged = fold_case(low.id, high.id, ["same landmark"], merged_by="auto_suggest")
    assert merged.urgency_score >= 90
    assert "English jetty report" in (merged.summary or "") or any("English" in (q.text or "") for q in merged.report_quotes)


def test_malayalam_script_place_names_resolve_to_a_landmark():
    geo = gazetteer.lookup("കൈനകരി ബോട്ട് ജെട്ടി")
    assert geo.landmark_id == "LM-02"
    assert geo.is_low_confidence is False
    assert geo.ward_id == "ward_1"
    place = extract_place("കൈനകരി ബോട്ട് ജെട്ടിയിൽ ആളുകൾ കുടുങ്ങി")
    assert place and "കൈനകരി" in place
    named = [lm for lm in gazetteer.landmarks if lm["id"].startswith("LM-") and int(lm["id"].split("-")[1]) <= 15]
    assert sum(1 for lm in named if lm.get("aliases_ml")) >= 15


def test_near_the_bridge_does_not_jump_to_wayanad():
    geo = gazetteer.lookup("near the bridge")
    assert geo.is_low_confidence is True
    assert geo.ward_id is None
    assert geo.landmark_id is None
    vague = gazetteer.lookup("പാലം")
    assert vague.is_low_confidence is True
    assert vague.ward_id != "ward_11"


def test_people_on_the_roof_is_not_a_water_depth():
    for text in ("people on the roof", "stuck on the roof", "छत पर 4 लोग फंसे हैं", "12 of us are trapped, child not breathing"):
        got = depth_from_text(text)
        assert got is None or got["band"] != "roof"
    checked = validate_depth("roof", "छत पर", "छत पर 4 लोग फंसे हैं", "gemini")
    assert checked["band"] == "unknown"
    water = depth_from_text("water up to the roof")
    assert water and water["band"] == "roof"
    floor = depth_from_text("water up to the first floor")
    assert floor and floor["band"] == "floor"


def test_twelve_of_us_is_not_the_child_subgroup():
    text = "12 of us are trapped at Kainakary Boat Jetty, child not breathing"
    assert people_count(text) == 12
    assert people_count("12 of us are trapped, a child is not breathing") == 12
    assert people_count("we are 12") == 12
    assert people_count("हम बारह लोग") == 12
    assert people_count("പന്ത്രണ്ട് പേർ") == 12


def test_chest_deep_rescue_is_not_offered_a_road_ambulance():
    storage_service.load_seed_resources()
    req = StoredRequest(
        id="req_chest_jetty",
        type=IncidentType.RESCUE,
        place_text="Kainakary Boat Jetty",
        raw_text="Chest-deep water at Kainakary Boat Jetty, people trapped, send a boat",
        lat=KAINAKARY["lat"],
        lng=KAINAKARY["lng"],
        people_count=4,
        hazard=HazardType.WATER_RISING,
    )
    out = no_team_options(req, storage_service.list_resources())
    assert out["options"]["road"] is None


def test_route_eta_uses_the_same_speed_as_the_proposal():
    assert eta_for_distance(0.94, "road") == 3
    assert eta_for_distance(4.3, "road") == 13
    command = (ROOT / "apps/web/src/app/coordinator/pages/command/coordinator-command.component.ts").read_text(encoding="utf-8")
    assert "/ 12" not in command
    assert "/ 30 * 60" not in command
    assert "fallbackEta" in command


def test_toast_and_panel_name_the_approved_team():
    command = (ROOT / "apps/web/src/app/coordinator/pages/command/coordinator-command.component.ts").read_text(encoding="utf-8")
    html = (ROOT / "apps/web/src/app/coordinator/pages/command/coordinator-command.component.html").read_text(encoding="utf-8")
    start = command.find("approveMatch(prop: MatchProposal")
    approve = command[start:start + 2800]
    assert "selectRequest(next" not in approve
    assert "pickedMatch.set(prop.request_id, prop.match_id)" in approve
    selected = command.split("readonly selectedRequest", 1)[1].split("matchesFor", 1)[0]
    assert "list[0]" not in selected
    assert "this.requests().find" in selected
    assert "assignedTeam(req)" in html
    assert "e.key === 'Escape'" in command
    escape = command.split("onKey", 1)[1][:1200]
    assert escape.find("e.key === 'Escape'") < escape.find("traceRequestId()")


def test_conflicting_counts_at_the_same_jetty_are_held_for_review():
    token = f"Chalakudy{uuid.uuid4().hex[:4]}"
    first = _post(f"4 people stranded at Chalakudy River Jetty, send a boat {token}", {"lat": 10.30315, "lng": 76.32747}, f"ch-{token}-a")
    second = _post(f"6 people stranded at Chalakudy River Jetty, send a boat {token}", {"lat": 10.30315, "lng": 76.32747}, f"ch-{token}-b")
    assert first["dedupe_decision"] == "new"
    assert second["dedupe_decision"] != "duplicate"
    cards = _cards(token)
    assert len(cards) == 2
    assert sorted(card["people_count"] for card in cards) == [4, 6]
    assert any("Counts differ" in ((card.get("count_note") or "") + (card.get("dedupe_trace") or "")) for card in cards)


def test_a_report_with_no_place_is_not_joined_as_the_same_place():
    text = "Forward this message. Free rescue kit. bit.ly/not-a-place otp 1234"
    a = _post(text, None, f"hoax-{uuid.uuid4().hex[:8]}") if False else None
    body = {
        "text": text,
        "raw_text": text,
        "lang": "en",
        "channel": "text",
        "idempotency_key": f"hoax-{uuid.uuid4().hex[:8]}",
    }
    first = client.post("/api/reports", json=body)
    body["idempotency_key"] = f"hoax-{uuid.uuid4().hex[:8]}"
    second = client.post("/api/reports", json=body)
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["dedupe_decision"] != "duplicate"
    assert second.json()["dedupe_decision"] != "duplicate"
    listed = client.get("/api/requests", headers=AUTH).json()
    copies = [row for row in listed if (row.get("raw_text") or "") == text]
    assert len(copies) == 1
    assert copies[0]["merged_count"] == 1
    assert "same place" not in (copies[0].get("dedupe_trace") or "").lower()


def test_explainer_uses_plain_words_and_call_112_for_a_life_threat():
    req = StoredRequest(
        id="req_breath",
        type=IncidentType.RESCUE,
        raw_text="child not breathing at Kainakary Boat Jetty",
        people_count=2,
        lat=9.47,
        lng=76.39,
    )
    resource = storage_service.list_resources()[0]
    breakdown = MatchBreakdown(
        distance_km=1.2, distance_score=10, capacity_fit_score=10,
        urgency_score=20, vulnerability_fit_score=5, total_score=45,
    )
    text = explainer_agent.generate_template_fallback(req, resource, breakdown).text_en
    assert "urgency_score" not in text and "match_score" not in text
    assert "112" in text


def test_matching_is_stable_and_medical_radius_is_not_applied_to_rescue():
    storage_service.load_seed_resources()
    rescue = StoredRequest(id="req_stable_rescue", type=IncidentType.RESCUE, lat=9.436, lng=76.398, people_count=4)
    first = [p.resource_id for p in matching_agent.find_matches(rescue, save_to_storage=False)]
    second = [p.resource_id for p in matching_agent.find_matches(rescue, save_to_storage=False)]
    assert first and first == second
    medical = StoredRequest(id="req_stable_med", type="medical", lat=9.478, lng=76.399, people_count=2)
    med = matching_agent.find_matches(medical, save_to_storage=False)
    assert med and all(p.breakdown.distance_km <= 25 for p in med)


def test_desk_answer_cites_only_returned_kainakary_refs():
    from app.agents import desk_query as dq

    rows = [
        StoredRequest(id="k1", ward_id="ward_1", type="rescue", public_code="RD-3866", urgency_score=80,
                      vulnerable={"elderly": True}, status="new"),
        StoredRequest(id="a1", ward_id="ward_4", type="rescue", public_code="RD-0001", urgency_score=80,
                      vulnerable={"elderly": True}, status="new"),
    ]
    filters = dq.rule_filters("which elderly cases in Kainakary are still waiting?")
    assert filters["ward_ids"] == ["ward_1"]
    out = dq.ask("which elderly cases in Kainakary are still waiting?", rows, call=lambda *_: (_ for _ in ()).throw(RuntimeError("no gemini")))
    refs = {c["ref"] for c in out["cases"]}
    mentioned = set(re.findall(r"RD-\d+", out["answer"] or ""))
    assert mentioned <= refs
    assert "RD-0001" not in (out["answer"] or "")
    assert "RD-3866" in (out["answer"] or "")


def test_malayalam_report_is_asked_in_malayalam():
    from app.agents.chat_intake import chat_intake_agent

    reply = chat_intake_agent.process_turn(None, "ഞങ്ങൾ കുടുങ്ങി", lang_override="en")
    assert re.search(r"[\u0D00-\u0D7F]", reply.bot_message)


def test_public_alert_is_not_a_dog_attack_sample():
    alerts = client.get("/api/public/alerts").json()
    alt = next(row for row in alerts if row["id"] == "alt_01")
    assert "Ward 9" in alt["ward"]
    assert "dog" not in alt["title"].lower()
    assert "dog" not in alt["description"].lower()


def test_dismissed_hoax_is_not_completed():
    from app.models.firestore_models import RequestStatus

    req = StoredRequest(id=f"hoax_{uuid.uuid4().hex[:6]}", type=IncidentType.RESCUE, raw_text="spam bit.ly otp", status=RequestStatus.NEW)
    req.flags = ["likely_hoax"]
    storage_service.save_request(req)
    out = storage_service.dismiss_hoax(req.id, actor="test")
    assert out.status.value == "dismissed_hoax"
    assert out.status.value != "completed"
    assert out.status.value != "closed"
