"""Judge r6 fix #1: flag (never auto-merge) on the structured record, rated from merged facts."""
from fastapi.testclient import TestClient

from app.agents import pipeline
from app.main import app
from app.tools.storage import storage_service

client = TestClient(app)
AUTH = {"Authorization": "Bearer demo-coordinator-token"}


def _send(text, lang, pin):
    res = client.post("/api/reports", json={"text": text, "lang": lang, "location_pin": pin})
    assert res.status_code in (200, 201), res.text
    pipeline.wait_for_idle(20)
    return storage_service.get_request(res.json()["request_id"])


def test_judge_live_sequence_is_flagged_and_scored_within_5():
    client.post("/api/demo/full", headers=AUTH)
    manglish = _send("Kainakary boat jetty aduthu 3 per kudungi, vellam nenju vare, oru appooppan undu, boat venam",
                     "en", {"lat": 9.4700, "lng": 76.3900})
    english = _send("4 people stuck near Kainakary boat jetty, water at chest level, an old man with us, need a boat",
                    "en", {"lat": 9.47185, "lng": 76.39571})  # ~430 m away, as on the live desk
    hint = english.possible_duplicate
    assert hint and not english.merged_into
    assert hint.target_id == manglish.id
    assert "landmark" in hint.signals
    assert hint.plan_people == 4 and any("3 vs 4 people → plan for 4" in d for d in hint.differences)
    a = storage_service.get_request(manglish.id).urgency_score
    assert english.urgency_score >= a - 0.01
    assert abs(a - english.urgency_score) <= 5, (a, english.urgency_score)
    malayalam = _send("കൈനകരി ബോട്ട് ജെട്ടിക്ക് അടുത്ത് 3 പേർ കുടുങ്ങി, വെള്ളം നെഞ്ചോളം, ഒരു അപ്പൂപ്പൻ ഉണ്ട്", "ml",
                      {"lat": 9.4705, "lng": 76.3910})
    assert malayalam.possible_duplicate is not None or malayalam.merged_into, (malayalam.dedupe_trace, malayalam.place_text, malayalam.ward_id)


def test_other_side_of_the_canal_is_never_high_and_shows_differences():
    client.post("/api/demo/full", headers=AUTH)
    _send("Kainakary boat jetty aduthu 3 per kudungi, vellam nenju vare, oru appooppan undu", "en", {"lat": 9.4700, "lng": 76.3900})
    other = _send("Kainakary jetty, other side of the canal, 2 people, pregnant woman", "en", {"lat": 9.4712, "lng": 76.3935})
    hint = other.possible_duplicate
    if hint is not None:
        assert hint.level != "High"
        text = " ".join(hint.differences)
        assert "2 vs 3" in text or "3 vs 2" in text
        assert "pregnant" in text and "other side" in text


def test_seeded_possible_duplicate_shows_signals_and_plans_for_the_hero_count():
    client.post("/api/demo/full", headers=AUTH)
    dup = storage_service.get_request("DEMO-110")
    assert dup.possible_duplicate and dup.possible_duplicate.signals
    assert dup.possible_duplicate.plan_people == 8
