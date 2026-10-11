"""Hinglish and Hindi intake must keep the place, the ward, and who is vulnerable."""
from fastapi.testclient import TestClient
from app.agents.intake import intake_agent
from app.main import app
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
