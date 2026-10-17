"""The chat stops asking on the first life-threat words, in any language, and keeps the original sentence apart."""
import pytest

from app.agents.chat_intake import ChatIntakeAgent


@pytest.mark.parametrize("text,lang,expect", [
    ("My son is not breathing, water is chest deep", "en", "Call 112 now"),
    ("അച്ഛൻ ശ്വസിക്കുന്നില്ല, വീടിന് ചുറ്റും വെള്ളം", "ml", "112"),
    ("मेरे पिता सांस नहीं ले रहे", "hi", "112"),
])
def test_first_life_trigger_stops_questions(text, lang, expect):
    agent = ChatIntakeAgent()
    resp = agent.process_turn(None, text, lang_override=lang)
    assert resp.confirmation_card is not None, resp.bot_message
    assert resp.missing_fields == []
    card = resp.confirmation_card
    assert card.life_threat and card.life_phrase
    assert expect in resp.bot_message
    assert card.original_text == text and card.answers == []


def test_life_trigger_on_a_later_turn_stops_there_and_keeps_answers_apart():
    agent = ChatIntakeAgent()
    first = agent.process_turn(None, "Water entering our house near Nedumudi", lang_override="en")
    assert first.confirmation_card is None  # still asking
    second = agent.process_turn(first.session_id, "my father is not breathing", lang_override="en")
    card = second.confirmation_card
    assert card is not None and card.life_threat
    assert card.original_text == "Water entering our house near Nedumudi"
    assert card.answers == ["my father is not breathing"]


def test_report_keeps_chat_answers_apart_from_the_original_sentence():
    from fastapi.testclient import TestClient

    from app.main import app
    from app.tools.storage import storage_service

    client = TestClient(app)
    res = client.post("/api/reports", json={
        "text": "Water entering our house near Nedumudi\\nmy father is not breathing",
        "raw_text": "Water entering our house near Nedumudi",
        "chat_answers": ["my father is not breathing"],
        "location_pin": {"lat": 9.43, "lng": 76.4},
        "structured": {"incident_type": "medical", "place_text": "Nedumudi", "people_count": 1},
    })
    assert res.status_code in (200, 201), res.text
    report = storage_service.get_report(res.json()["report_id"])
    assert report.raw_text == "Water entering our house near Nedumudi"
    assert report.chat_answers == ["my father is not breathing"]


def test_life_words_in_a_chat_answer_put_the_case_in_the_lane():
    from fastapi.testclient import TestClient

    from app.main import app
    from app.tools.case_queue import is_life_threat
    from app.tools.storage import storage_service

    client = TestClient(app)
    res = client.post("/api/reports", json={
        "text": "Water entering our house near Kainakary\\nmy father is not breathing",
        "raw_text": "Water entering our house near Kainakary",
        "chat_answers": ["my father is not breathing"],
        "location_pin": {"lat": 9.47, "lng": 76.39},
        "structured": {"incident_type": "medical", "place_text": "Kainakary", "people_count": 1},
    })
    assert is_life_threat(storage_service.get_request(res.json()["request_id"]))
