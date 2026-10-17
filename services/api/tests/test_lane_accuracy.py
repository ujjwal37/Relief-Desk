"""Judge r6 item 3: oxygen and labour enter the lane, 'water came in' is not a depth, place names in English."""
from app.agents.depth import fill_depth
from app.tools.case_queue import life_phrase
from app.tools.place_names import english_place


def test_oxygen_and_labour_trigger_the_lane_in_five_languages():
    for text in ("My father's oxygen is running out, water all around", "She is in labour and we are stuck",
                 "पापा का ऑक्सीजन खत्म हो रहा है", "Biwi ko labour pain shuru, paani bhara hai", "oxygen khatam hone wala hai",
                 "അമ്മയുടെ ഓക്സിജൻ തീരാറായി", "ചേച്ചിക്ക് പ്രസവവേദന തുടങ്ങി", "ammachikku oxygen theerarayi", "chechikku prasava vedana"):
        assert life_phrase(text), text


def test_water_came_in_is_not_a_depth():
    class R:  # minimal case
        raw_text = "ചമ്പക്കുളം പള്ളിക്ക് അടുത്ത് വെള്ളം കയറി"
        report_quotes = []
        place_text = "Champakulam church"
        water_depth = {"band": "floor", "quote": "വെള്ളം കയറി", "source": "gemini"}
    r = R()
    fill_depth(r)
    assert r.water_depth["band"] == "unknown"


def test_quoted_real_depth_is_kept():
    class R:
        raw_text = "water up to the first floor"
        report_quotes = []
        place_text = ""
        water_depth = {"band": "floor", "quote": "water up to the first floor", "source": "gemini"}
    r = R()
    fill_depth(r)
    assert r.water_depth["band"] == "floor"


def test_malayalam_place_names_read_in_english_and_doubled_words_go():
    assert english_place("ചമ്പക്കുളം പള്ളി") == "Champakulam church"
    assert english_place("Nedumudi Bridge bridge") == "Nedumudi Bridge"
