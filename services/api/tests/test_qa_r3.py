"""QA round 3: chat intake, shelter classification, rising water, alerts, info close.

No test calls Gemini.
"""
import uuid

from fastapi.testclient import TestClient

from app.agents.chat_intake import ChatIntakeAgent
from app.agents.intake import extract_with_rules
from app.main import app
from app.models.firestore_models import HazardType, IncidentType, RequestStatus, StoredRequest
from app.models.schemas import IncidentType as SchemaType
from app.tools.anomaly import acknowledge, collect_alerts, unacknowledge
from app.tools.nlu_rules import extract_place, is_nobody_stranded, place_is_usable
from app.tools.scoring import scoring_engine
from app.tools.storage import storage_service
from app.tools.translation import faithful_english, translation_drops_facts, translation_service

client = TestClient(app)
AUTH = {"Authorization": "Bearer demo-coordinator-token"}

SHELTER = "Shelter needed tonight for 12 people, including a pregnant woman"
RISING = "Pulincunnu il 4 per und, vellam koodunnu"
GENERIC = "Emergency report: flood water rising, people requesting urgent assistance."


def test_nobody_stranded_ends_without_another_question_or_higher_ground():
    agent = ChatIntakeAgent()
    text = "Nobody is stranded in Pulincunnu ward 3"
    first = agent.process_turn(None, text, scenario_id="flood", lang_override="en")
    assert first.confirmation_card is not None
    assert first.missing_fields == []
    assert "how many" not in first.bot_message.lower()
    assert "higher ground" not in first.bot_message.lower()
    assert "higher ground" not in (first.safety_line or "").lower()
    assert "higher ground" not in (first.confirmation_card.safety_line or "").lower()
    card = first.confirmation_card
    assert card.incident_type == "info"
    assert card.people_count is None
    assert "pulincunnu" in (card.place_text or "").lower()
    assert card.place_text.lower().strip() != "ward 3"
    assert "nobody is stranded" in card.summary.lower()
    assert "none of these" not in card.summary.lower()
    assert "how many" not in card.summary.lower()
    assert is_nobody_stranded(text)


def test_chat_asks_where_and_does_not_repeat_or_keep_junk_places():
    agent = ChatIntakeAgent()
    session = f"vague-{uuid.uuid4().hex[:6]}"
    opened = agent.process_turn(
        session,
        "please help water coming in fast near the bridge",
        scenario_id="flood",
        lang_override="en",
    )
    assert opened.confirmation_card is None
    assert opened.missing_fields[0] == "location"
    assert "located" in opened.bot_message.lower() or "where" in opened.bot_message.lower()
    assert agent._sessions[session].extracted_so_far.place_text in (None, "")
    assert not place_is_usable("the bridge")
    assert not place_is_usable("people near Edathua church")
    edathua = extract_place("2 people near Edathua church")
    assert edathua and "edathua" in edathua.lower() and "people" not in edathua.lower()

    junk = agent.process_turn(session, "asdfqwerty", scenario_id="flood", lang_override="en")
    assert junk.missing_fields[0] != "location"
    assert "located" not in junk.bot_message.lower()
    assert "where are you" not in junk.bot_message.lower()


def test_typed_answers_fill_need_and_water_without_a_repeat():
    agent = ChatIntakeAgent()
    session = f"typed-{uuid.uuid4().hex[:6]}"
    agent.process_turn(session, "please help", scenario_id="flood", lang_override="en")
    located = agent.process_turn(session, "Kainakary", scenario_id="flood", lang_override="en")
    assert "kainakary" in (agent._sessions[session].extracted_so_far.place_text or "").lower()
    assert located.missing_fields[0] == "people_count"
    counted = agent.process_turn(session, "4", scenario_id="flood", lang_override="en")
    assert "people_count" not in counted.missing_fields
    if "need" in counted.missing_fields:
        needed = agent.process_turn(session, "shelter", scenario_id="flood", lang_override="en")
        assert "need" not in needed.missing_fields
        assert agent._sessions[session].extracted_so_far.type == SchemaType.SHELTER
        assert "what do you need" not in needed.bot_message.lower()
    boat = ChatIntakeAgent().process_turn(
        None, "Kainakary il 4 per und, boat venam", scenario_id="flood", lang_override="en"
    )
    assert boat.confirmation_card is None or "what do you need" not in boat.bot_message.lower()
    assert "what do you need" not in boat.bot_message.lower()


def test_summary_is_the_report_not_the_quick_replies():
    agent = ChatIntakeAgent()
    session = "sum-qa"
    agent.process_turn(session, "The road is flooded in Pulincunnu.", scenario_id="flood", lang_override="en")
    agent.process_turn(session, "None of these", scenario_id="flood", lang_override="en")
    done = agent.process_turn(session, "I am not sure how many people", scenario_id="flood", lang_override="en")
    # A third question may still be open. Force the card by answering the rest with shrugs.
    if done.confirmation_card is None:
        done = agent.process_turn(session, "No", scenario_id="flood", lang_override="en")
    if done.confirmation_card is None:
        done = agent.process_turn(session, "No", scenario_id="flood", lang_override="en")
    assert done.confirmation_card is not None
    summary = done.confirmation_card.summary.lower()
    assert "road is flooded" in summary
    assert "none of these" not in summary
    assert "not sure" not in summary


def test_english_shelter_for_twelve_is_shelter_not_other():
    extracted = extract_with_rules(SHELTER)
    assert extracted.type == SchemaType.SHELTER
    assert extracted.people.count == 12
    assert extracted.vulnerable.pregnant is True
    token = uuid.uuid4().hex[:8]
    response = client.post(
        "/api/reports",
        json={"text": SHELTER, "lang": "en", "idempotency_key": f"shelter-{token}"},
    )
    assert response.status_code == 200, response.text
    stored = storage_service.get_request(response.json()["request_id"])
    assert stored is not None
    assert stored.type == IncidentType.SHELTER
    assert stored.people_count == 12
    assert stored.vulnerable.pregnant is True
    assert "not stated" not in (stored.urgency_reason or "").lower()


def test_rising_water_with_people_is_not_a_low_priority():
    assert translation_drops_facts(RISING, GENERIC)
    fixed = faithful_english(RISING)
    assert "4" in fixed
    assert "pulincunnu" in fixed.lower()
    assert fixed != GENERIC
    fallback = translation_service._deterministic_fallback(RISING, "ml")
    assert "4" in fallback.text_en
    assert "pulincunnu" in fallback.text_en.lower()

    req = StoredRequest(
        id="rise-1",
        type=IncidentType.RESCUE,
        people_count=4,
        hazard=HazardType.NONE,
        raw_text=RISING,
        summary=RISING,
        ai_translation=GENERIC,
        place_text="Pulincunnu",
    )
    scored = scoring_engine.compute_urgency(req)
    assert scored.score >= 60
    assert scored.tier == "urgent"
    assert "no immediate life threat" not in scored.reason.lower()

    token = uuid.uuid4().hex[:8]
    response = client.post(
        "/api/reports",
        json={"text": RISING, "lang": "en", "idempotency_key": f"rise-{token}"},
    )
    assert response.status_code == 200, response.text
    stored = storage_service.get_request(response.json()["request_id"])
    assert stored is not None
    assert stored.people_count == 4
    assert "4" in (stored.ai_translation or "")
    assert stored.urgency_score >= 60
    assert "no immediate life threat" not in (stored.urgency_reason or "").lower()


def test_close_info_is_not_counted_as_a_rescue():
    token = uuid.uuid4().hex[:8]
    response = client.post(
        "/api/reports",
        json={
            "text": "Nobody is stranded in Pulincunnu",
            "lang": "en",
            "idempotency_key": f"info-{token}",
        },
    )
    assert response.status_code == 200, response.text
    request_id = response.json()["request_id"]
    closed = client.post(f"/api/requests/{request_id}/close-info", headers=AUTH)
    assert closed.status_code == 200, closed.text
    body = closed.json()
    assert body["status"] == "info_closed"
    assert not body.get("assigned_resource_id")
    stored = storage_service.get_request(request_id)
    assert stored is not None
    assert stored.status == RequestStatus.INFO_CLOSED
    from app.agents.dispatcher import list_open_cases

    assert request_id not in {row["id"] for row in list_open_cases()}


def test_alert_without_a_ward_can_be_unacknowledged():
    alerts = collect_alerts(storage_service)
    gap = next(item for item in alerts if item.kind == "resource_gap" and item.ward_id is None)
    acknowledge(gap.id)
    acknowledged = next(item for item in collect_alerts(storage_service) if item.id == gap.id)
    assert acknowledged.acknowledged is True
    denied = client.post(f"/api/alerts/{gap.id}/unacknowledge")
    assert denied.status_code == 401
    cleared = client.post(f"/api/alerts/{gap.id}/unacknowledge", headers=AUTH)
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["acknowledged"] is False
    unacknowledge(gap.id)
