"""Citizen chat intake: hoax hold, slot filling, negation, and truthful summaries.

These tests run with no API key. The Gemini path is a mocked client.
"""
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from app.agents.chat_intake import ChatIntakeAgent
from app.agents.intake import SYSTEM_INTAKE_PROMPT, IntakeAgent, extract_with_rules
from app.agents.summary import guard_summary, summary_from_report, unstated_conditions
from app.main import app
from app.models.schemas import IncidentType
from app.tools.nlu_rules import hazard_name, infer_incident_type, parse_people_reply
from app.tools.storage import storage_service

client = TestClient(app)

DIABETIC = (
    "Elderly father having severe diabetic emergency near Kainakary LP School, "
    "house surrounded by chest-deep flood water."
)
HOAX = "URGENT free rescue in bit.ly/help send OTP now to confirm the helicopter"
PULINCUNNU = "Nobody is stranded in Pulincunnu"


def test_hoax_chat_is_held_and_does_not_use_the_last_answer():
    agent = ChatIntakeAgent()
    session = "hoax-chat"
    first = agent.process_turn(session, HOAX, scenario_id="flood", lang_override="en")
    assert first.confirmation_card is not None
    assert first.held is True
    assert first.likely_hoax is True
    assert first.hoax_reason
    assert "bit.ly" in first.hoax_reason or "otp" in first.hoax_reason.lower()
    card = first.confirmation_card
    assert card.held is True
    assert card.likely_hoax is True
    assert (card.place_text or "").lower() != "bit"
    assert "bit.ly" not in (card.place_text or "").lower()
    assert card.people_count is None
    assert card.summary.strip() != "No"
    assert "bit.ly" in card.summary.lower()
    assert "otp" in card.summary.lower()
    assert "hoax" in first.bot_message.lower() or "held" in first.bot_message.lower()
    assert "112" in first.bot_message

    # A later "No" must not become the case summary.
    again = agent.process_turn(session, "No", scenario_id="flood", lang_override="en")
    assert again.confirmation_card is not None
    assert again.confirmation_card.summary.strip() != "No"
    assert "bit.ly" in again.confirmation_card.summary.lower()
    assert again.confirmation_card.people_count is None
    assert (again.confirmation_card.place_text or "").lower() != "bit"


def test_bad_chat_card_is_repaired_on_submit_and_held():
    text = f"{HOAX}\nNo"
    token = uuid.uuid4().hex[:8]
    response = client.post(
        "/api/reports",
        json={
            "text": text,
            "raw_text": text,
            "lang": "en",
            "channel": "text",
            "idempotency_key": f"hoax-card-{token}",
            "structured": {
                "incident_type": "rescue",
                "place_text": "bit",
                "people_count": 0,
                "hazard": "unknown",
                "summary": "No",
            },
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "hoax" in body["flags"]
    assert "likely_hoax" in body["flags"]
    stored = storage_service.get_request(body["request_id"])
    assert stored is not None
    assert "hoax" in stored.flags
    assert "likely_hoax" in stored.flags
    assert stored.hoax_reason
    assert (stored.place_text or "").lower() != "bit"
    assert stored.people_count is None
    assert (stored.summary or "").strip() != "No"
    assert "bit.ly" in (stored.summary or "").lower() or "otp" in (stored.summary or "").lower()
    assert "insulin" not in (stored.summary or "").lower()
    assert storage_service.list_matches_for_request(stored.id) == []


@pytest.mark.parametrize(
    "text",
    [
        "Nobody is stranded in Pulincunnu",
        "Pulincunnu mein koi stranded nahi hai",
        "Pulincunnu में कोई फंसा नहीं है",
        "Pulincunnu-il ആരും stranded അല്ല",
    ],
)
def test_negation_keeps_pulincunnu_and_is_not_a_rescue(text):
    assert infer_incident_type(text) != "rescue"
    extracted = extract_with_rules(text)
    assert extracted.type != IncidentType.RESCUE
    assert extracted.place_text is not None
    assert "pulincunnu" in extracted.place_text.lower()
    assert extracted.people.count is None


def test_chat_asks_location_before_people_and_keeps_typed_counts():
    answers = [
        ("en", "five", 5),
        ("en", "5", 5),
        ("hi", "पाँच", 5),
        ("hi", "५", 5),
        ("hinglish", "paanch", 5),
        ("hinglish", "teen log", 3),
        ("ml", "അഞ്ച്", 5),
        ("ml", "൫", 5),
        ("ml", "5 പേർ", 5),
    ]
    for lang, answer, expected in answers:
        agent = ChatIntakeAgent()
        session = f"slots-{lang}-{expected}-{uuid.uuid4().hex[:4]}"
        opened = agent.process_turn(
            session,
            "please help, water is in the house",
            scenario_id="flood",
            lang_override=lang,
        )
        assert opened.confirmation_card is None
        assert opened.missing_fields[0] == "location"
        assert "how many" not in opened.bot_message.lower()
        assert "कितने" not in opened.bot_message

        located = agent.process_turn(session, "Pulincunnu", scenario_id="flood", lang_override=lang)
        assert located.confirmation_card is None
        assert located.missing_fields[0] == "people_count"
        assert "pulincunnu" in (agent._sessions[session].extracted_so_far.place_text or "").lower()

        counted = agent.process_turn(session, answer, scenario_id="flood", lang_override=lang)
        assert agent._sessions[session].extracted_so_far.people.count == expected
        assert "people_count" not in counted.missing_fields
        assert "how many" not in counted.bot_message.lower()
        assert "कितने" not in counted.bot_message
        if counted.confirmation_card is not None:
            assert counted.confirmation_card.people_count == expected
            assert counted.confirmation_card.summary.strip() != answer
            assert "please help" in counted.confirmation_card.summary.lower()


@pytest.mark.parametrize(
    "answer",
    [
        "I am not sure how many people",
        "मुझे पता नहीं कितने लोग हैं",
        "Mujhe nahi pata kitne log hain",
        "എത്ര പേരെന്ന് എനിക്ക് ഉറപ്പില്ല",
    ],
)
def test_unknown_people_stays_null(answer):
    assert parse_people_reply(answer) == ("unknown", None)
    agent = ChatIntakeAgent()
    session = f"unknown-{uuid.uuid4().hex[:6]}"
    agent.process_turn(session, "send a boat, water is rising", scenario_id="flood", lang_override="en")
    agent.process_turn(session, "Kainakary", scenario_id="flood", lang_override="en")
    replied = agent.process_turn(session, answer, scenario_id="flood", lang_override="en")
    assert "people_count" not in replied.missing_fields
    assert agent._sessions[session].extracted_so_far.people.count is None
    if replied.confirmation_card is not None:
        assert replied.confirmation_card.people_count is None
        assert replied.confirmation_card.summary.strip() != answer


def test_water_already_stated_is_not_asked_again():
    assert hazard_name("vellam koodunnu") == "water_rising"
    assert hazard_name("വെള്ളം കൂടുന്നു") == "water_rising"
    assert hazard_name("paani badh raha hai") == "water_rising"
    agent = ChatIntakeAgent()
    message = "Pulincunnu il 4 per und, vellam koodunnu, please send a boat"
    resp = agent.process_turn("water-ml", message, scenario_id="flood", lang_override="en")
    assert "is the water" not in resp.bot_message.lower()
    assert "rising" not in resp.bot_message.lower()
    assert "വെള്ളം ഉയരുകയാണോ" not in resp.bot_message
    assert resp.confirmation_card is not None
    assert resp.confirmation_card.people_count == 4
    assert "pulincunnu" in (resp.confirmation_card.place_text or "").lower()
    assert resp.confirmation_card.hazard == "water_rising"
    assert resp.confirmation_card.summary.strip() != "No"
    # A short summary built from what the reporter said, not the transcript.
    assert "4" in resp.confirmation_card.summary and "pulincunnu" in resp.confirmation_card.summary.lower()


def test_summary_uses_the_report_not_the_last_reply():
    report = f"{HOAX}\nNo"
    summary = summary_from_report(report, "No")
    assert summary.strip() != "No"
    assert "bit.ly" in summary.lower()
    assert "otp" in summary.lower()


def test_rules_summary_does_not_rename_diabetic_emergency():
    summary = guard_summary(DIABETIC, "Elderly father in acute insulin shock near the school.")
    assert "insulin shock" not in summary.lower()
    assert "diabetic emergency" in summary.lower()
    upgraded = unstated_conditions(DIABETIC, "acute insulin shock")
    assert "acute insulin shock" in upgraded
    assert "insulin shock" in upgraded
    extracted = extract_with_rules(DIABETIC)
    assert extracted.people.count is None
    filed = summary_from_report(DIABETIC, extracted.notes)
    assert "insulin shock" not in filed.lower()
    assert "severe diabetic emergency" in DIABETIC.lower()


def test_prompt_forbids_renaming_conditions():
    assert "severe diabetic emergency" in SYSTEM_INTAKE_PROMPT
    assert "insulin shock" in SYSTEM_INTAKE_PROMPT
    assert "must not" in SYSTEM_INTAKE_PROMPT


def test_mocked_gemini_summary_is_rewritten_when_it_upgrades_a_condition():
    class _Usage:
        provider = "gemini"

    class _Gemini:
        last_ai = _Usage()

        def generate_content(self, **_kwargs):
            return json.dumps(
                {
                    "type": "medical",
                    "place_text": "Kainakary LP School",
                    "people": {"count": 1, "confidence": 0.95},
                    "vulnerable": {
                        "child": False,
                        "elderly": True,
                        "disabled": False,
                        "pregnant": False,
                        "medical_need": True,
                    },
                    "hazard": "water_rising",
                    "urgency_hint": "critical",
                    "language": "en",
                    "is_update_phrase": False,
                    "confidence": {"type": 0.9, "place": 0.9, "people": 0.2, "vulnerable": 0.8, "urgency": 0.9},
                    "evidence_spans": {},
                    "notes": "model note",
                    "text_en": "Elderly father is in acute insulin shock near Kainakary LP School.",
                    "text_hi": "बुजुर्ग पिता को इंसुलिन शॉक है।",
                    "translation_confidence": 0.9,
                    "likely_hoax": False,
                    "hoax_reason": None,
                }
            )

    extracted = IntakeAgent(client=_Gemini()).parse_report(DIABETIC, language_hint="en")
    assert "insulin shock" not in (extracted.text_en or "").lower()
    assert "diabetic emergency" in (extracted.text_en or "").lower()
    # The report never says how many people, so 1 must not be invented.
    assert extracted.people.count is None


def test_fallback_submit_keeps_the_stated_condition():
    token = uuid.uuid4().hex[:8]
    response = client.post(
        "/api/reports",
        json={
            "text": DIABETIC,
            "raw_text": DIABETIC,
            "lang": "en",
            "channel": "text",
            "idempotency_key": f"diabetic-{token}",
        },
    )
    assert response.status_code == 200, response.text
    stored = storage_service.get_request(response.json()["request_id"])
    assert stored is not None
    blob = " ".join(filter(None, [stored.summary, stored.ai_translation, response.json().get("summary")]))
    assert "insulin shock" not in blob.lower()
    assert "diabetic" in blob.lower()
    assert stored.people_count is None
