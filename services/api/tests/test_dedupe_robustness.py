"""Reworded reports merge. Conflicting counts wait for a person. Weak matches wait."""
import uuid

from fastapi.testclient import TestClient

from app.agents.dedupe import AUTO_MERGE_CONFIDENCE, REVIEW_CONFIDENCE, dedupe_agent
from app.agents.intake import intake_agent
from app.main import app
from app.models.firestore_models import StoredRequest
from app.models.schemas import DedupeDecisionType, IncidentType

client = TestClient(app)
AUTH = {"Authorization": "Bearer demo-coordinator-token"}
PIN = {"lat": 8.11, "lng": 77.21}


def _post(text: str, pin: dict, key: str, structured: dict | None = None):
    body = {
        "text": text,
        "raw_text": text,
        "lang": "en",
        "channel": "text",
        "location_pin": pin,
        "idempotency_key": key,
    }
    if structured:
        body["structured"] = structured
    response = client.post("/api/reports", json=body)
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
        or any(needle in (quote.get("text") or "").lower() for quote in row.get("report_quotes") or [])
    ]


def test_three_reworded_reports_merge_into_one_case():
    token = f"Bramble{uuid.uuid4().hex[:6]}"
    texts = [
        f"4 people stranded on the roof at {token} jetty, send a boat",
        f"People stranded above the water at {token} jetty, send a rescue boat",
        f"Still stranded at {token} jetty, send a boat, people are on the roof",
    ]
    decisions = []
    for index, text in enumerate(texts):
        decisions.append(_post(text, PIN, f"rw-{token}-{index}")["dedupe_decision"])
    assert decisions == ["new", "duplicate", "duplicate"]
    cards = _cards(token)
    assert len(cards) == 1
    assert cards[0]["merged_count"] == 3
    quotes = [quote["text"] for quote in cards[0]["report_quotes"]]
    assert len(quotes) == 3
    assert all(any(piece in quote for quote in quotes) for piece in ("roof", "rescue boat", "Still stranded"))
    dedupe = next(step["output"] for step in cards[0]["trace"] if step["agent"] == "Dedupe")
    assert "Match evidence" in dedupe
    assert "km" in dedupe


def test_conflicting_people_ranges_use_the_higher_bound_and_keep_both_texts():
    """Head counts that disagree are not auto-merged. Each card keeps its own count."""
    token = f"Oakbend{uuid.uuid4().hex[:6]}"
    first = f"At {token} ghat, 2-3 people on the roof need a boat, send a rescue boat"
    second = f"{token} ghat: 4-5 people stranded, send a rescue boat"
    assert _post(first, PIN, f"rng-{token}-a")["dedupe_decision"] == "new"
    second_body = _post(second, PIN, f"rng-{token}-b")
    assert second_body["dedupe_decision"] != "duplicate"
    cards = _cards(token)
    assert len(cards) == 2
    counts = sorted(card["people_count"] for card in cards)
    assert counts == [3, 5]
    held = next(card for card in cards if card.get("possible_duplicate") or "Counts differ" in (card.get("dedupe_trace") or ""))
    assert "Counts differ" in (held.get("count_note") or held.get("dedupe_trace") or "")
    assert all(card["merged_count"] == 1 for card in cards)


def test_a_different_place_or_a_different_type_stays_separate():
    place = f"Northbend{uuid.uuid4().hex[:6]}"
    other = f"Southmarket{uuid.uuid4().hex[:6]}"
    _post(f"4 people stranded at {place} jetty, send a boat", PIN, f"pl-{place}")
    _post(
        f"4 people stranded at {other} market, send a boat",
        {"lat": 8.40, "lng": 77.80},
        f"pl-{other}",
    )
    assert len(_cards(place)) == 1
    assert len(_cards(other)) == 1
    assert _cards(place)[0]["merged_count"] == 1
    assert _cards(place)[0].get("possible_duplicate") in (None, {})

    shared = f"Samebend{uuid.uuid4().hex[:6]}"
    _post(f"4 people stranded at {shared} jetty, send a boat", PIN, f"ty-{shared}-r")
    medical = _post(
        f"A doctor is needed at {shared} jetty, medicine for 2 people",
        PIN,
        f"ty-{shared}-m",
        structured={
            "incident_type": "medical",
            "place_text": f"{shared} jetty",
            "people_count": 2,
            "hazard": "injury",
            "summary": f"Medicine at {shared} jetty",
        },
    )
    assert medical["dedupe_decision"] == "new"
    assert len(_cards(shared)) == 2


def test_a_weak_match_is_a_suggestion_until_the_coordinator_decides():
    token = f"Farjetty{uuid.uuid4().hex[:6]}"
    near = {"lat": 8.11, "lng": 77.21}
    apart = {"lat": 8.12, "lng": 77.21}
    _post(f"4 people stranded at {token} jetty, send a boat", near, f"wk-{token}-a")
    second = _post(f"People stranded at {token} jetty, send a rescue boat", apart, f"wk-{token}-b")
    assert second["dedupe_decision"] == "new"
    cards = _cards(token)
    assert len(cards) == 2
    suggestion = next(row for row in cards if row.get("possible_duplicate"))
    assert suggestion["possible_duplicate"]["target_id"]
    assert suggestion["possible_duplicate"]["confidence"] < AUTO_MERGE_CONFIDENCE
    assert suggestion["possible_duplicate"]["confidence"] >= REVIEW_CONFIDENCE
    dedupe = next(step["output"] for step in suggestion["trace"] if step["agent"] == "Dedupe")
    assert "Possible duplicate, review" in dedupe
    assert "Match evidence" in dedupe

    kept = client.post(f"/api/requests/{suggestion['id']}/keep-separate", headers=AUTH)
    assert kept.status_code == 200, kept.text
    again = _cards(token)
    assert all(not row.get("possible_duplicate") for row in again)
    assert len(again) == 2


def test_the_coordinator_can_merge_a_suggestion():
    token = f"Joinjetty{uuid.uuid4().hex[:6]}"
    _post(f"4 people stranded at {token} jetty, send a boat", PIN, f"jn-{token}-a")
    _post(
        f"People stranded at {token} jetty, send a rescue boat",
        {"lat": 8.12, "lng": 77.21},
        f"jn-{token}-b",
    )
    cards = _cards(token)
    assert len(cards) == 2
    copy = next(row for row in cards if row.get("possible_duplicate"))
    target = copy["possible_duplicate"]["target_id"]
    merged = client.post(
        f"/api/requests/{target}/merge",
        json={"secondary_request_id": copy["id"], "evidence": ["Coordinator confirmed"]},
        headers=AUTH,
    )
    assert merged.status_code == 200, merged.text
    left = _cards(token)
    assert len(left) == 1
    assert left[0]["id"] == target
    assert left[0]["merged_count"] == 2
    assert len(left[0]["report_quotes"]) == 2


def test_rules_do_not_merge_a_different_landmark_or_type():
    rescue = StoredRequest(
        id="req_rescue_place",
        type=IncidentType.RESCUE,
        place_text="Gandhi High School",
        raw_text="4 people stranded at Gandhi High School, send a boat",
        lat=9.45,
        lng=76.39,
        people_count=4,
    )
    other_place = "6 people stranded at Sangam market, send a boat"
    extracted = intake_agent.parse_report(other_place)
    decision = dedupe_agent.evaluate(other_place, extracted, [rescue], new_lat=9.45, new_lng=76.39)
    assert decision.decision == DedupeDecisionType.NEW
    assert decision.review is False

    medical = intake_agent.parse_report("doctor and medicine needed")
    medical.type = IncidentType.MEDICAL
    medical.place_text = "Gandhi High School"
    typed = dedupe_agent.evaluate(
        "doctor and medicine needed at Gandhi High School",
        medical,
        [rescue],
        new_lat=9.45,
        new_lng=76.39,
    )
    assert typed.decision == DedupeDecisionType.NEW
    assert typed.review is False
