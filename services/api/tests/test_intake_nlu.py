"""Hinglish and Hindi intake must keep the place, the ward, and who is vulnerable."""
from fastapi.testclient import TestClient
from app.agents.intake import SYSTEM_INTAKE_PROMPT, IntakeAgent, intake_agent
from app.main import app
from app.models.schemas import IncidentType
from app.tools.gazetteer import gazetteer
from app.tools.nlu_rules import infer_incident_type, people_count
from app.tools.storage import storage_service

client = TestClient(app)

HINGLISH = "Hamare ghar mein paani bhar gaya hai, 3 log hain, ek bujurg aur bachcha bhi, Ward 7 Temple Road"
HINDI = "हमारे घर में पानी भर गया है, 3 लोग हैं, एक बुजुर्ग और बच्चा भी, वार्ड 7 मंदिर रोड"
LANDMARK = "2 children stranded near Gandhi School, Ward 4, send a boat"


def test_hinglish_place_ward_and_child():
    extracted = intake_agent.parse_report(HINGLISH, language_hint="hinglish")
    assert extracted.place_text is not None
    assert "Ward 7" in extracted.place_text
    assert "Temple Road" in extracted.place_text
    assert "paani bhar" not in (extracted.place_text or "")
    assert extracted.people.count == 3
    assert extracted.vulnerable.child is True
    assert extracted.vulnerable.elderly is True


def test_hindi_place_ward_and_child():
    extracted = intake_agent.parse_report(HINDI, language_hint="hi")
    assert extracted.place_text is not None
    assert "वार्ड 7" in extracted.place_text
    assert extracted.people.count == 3
    assert extracted.vulnerable.child is True
    assert extracted.vulnerable.elderly is True


HINDI_FREE = "वार्ड 12 में 6 लोग फंसे हैं, एक बच्चा भी है, पानी बढ़ रहा है, नाव भेजो।"


class _BlankGemini:
    """A model answer that extracted nothing. Rules must still fill the facts."""

    def generate_content(self, **_kwargs):
        return "{}"


def test_hindi_free_text_reads_type_people_and_ward():
    assert people_count("वार्ड 3 में 10 लोगों के लिए खाना चाहिए") == 10
    assert people_count("चार लोग फंसे हैं") == 4
    assert people_count("वार्ड १२ में ६ लोग हैं") == 6
    assert infer_incident_type("नाव भेजो, लोग फंसे हैं") == "rescue"
    assert gazetteer.resolve_ward(None, "वार्ड १२ में पानी बढ़ रहा है") == "ward_12"

    extracted = intake_agent.parse_report(HINDI_FREE, language_hint="hi")
    assert extracted.type == IncidentType.RESCUE
    assert extracted.people.count == 6
    assert extracted.ward_id == "ward_12"
    assert extracted.vulnerable.child is True
    assert extracted.place_text is not None
    assert "वार्ड 12" in extracted.place_text


def test_rules_repair_a_blank_gemini_hindi_answer():
    assert "वार्ड" in SYSTEM_INTAKE_PROMPT
    assert "लोगों" in SYSTEM_INTAKE_PROMPT
    extracted = IntakeAgent(client=_BlankGemini()).parse_report(HINDI_FREE, language_hint="hi")
    assert extracted.type == IncidentType.RESCUE
    assert extracted.people.count == 6
    assert extracted.ward_id == "ward_12"
    assert extracted.vulnerable.child is True


def test_hindi_chat_confirms_type_people_and_ward():
    response = client.post(
        "/api/intake/chat",
        json={
            "session_id": "sess_hi_ward12",
            "message": HINDI_FREE,
            "language": "hi",
            "scenario_id": "flood",
        },
    )
    assert response.status_code == 200
    body = response.json()
    card = body["confirmation_card"]
    assert card is not None
    assert card["incident_type"] == "rescue"
    assert card["people_count"] == 6
    assert "वार्ड 12" in (card["place_text"] or "")
    assert "विवरण तैयार" in body["bot_message"]


def test_landmark_sentence_keeps_the_ward():
    extracted = intake_agent.parse_report(LANDMARK, language_hint="en")
    assert extracted.place_text is not None
    assert "Ward 4" in extracted.place_text
    assert extracted.vulnerable.child is True


def test_submit_stores_citizen_words_and_ward_id():
    response = client.post(
        "/api/reports",
        json={
            "text": HINGLISH,
            "raw_text": HINGLISH,
            "channel": "text",
            "lang": "hinglish",
            "idempotency_key": "idem_nlu_hinglish",
            "structured": {
                "incident_type": "rescue",
                "place_text": "paani bhar gaya hai, 3 log hain, ek bujurg aur bachcha bhi,",
                "people_count": 3,
                "vulnerable": {
                    "child": False,
                    "elderly": True,
                    "disabled": False,
                    "pregnant": False,
                    "medical_need": False,
                },
                "hazard": "water_rising",
                "summary": "3 persons needing rescue | at paani bhar | Vulnerable: elderly | Hazard: water_rising",
            },
        },
    )
    assert response.status_code == 200
    stored = storage_service.get_request(response.json()["request_id"])
    assert stored is not None
    assert stored.raw_text == HINGLISH
    assert stored.summary is not None
    assert "Hazard:" in stored.summary
    assert stored.ward_id == "ward_7"
    assert stored.place_text is not None
    assert "Temple Road" in stored.place_text
    assert stored.vulnerable.child is True
