"""Need-words set the incident type, and the ward comes from the landmark in the report."""
from app.agents.intake import intake_agent
from app.models.schemas import IncidentType
from app.tools.gazetteer import gazetteer
from app.tools.nlu_rules import infer_incident_type


def test_need_words_choose_the_type_not_the_place_name():
    assert infer_incident_type("2 log bimar hain oxygen aur dawa urgently chahiye") == "medical"
    assert infer_incident_type("25 log bhookhe hain ration aur drinking water packets bhejo") == "food"
    assert infer_incident_type("राशन और पीने का पानी खत्म हो गया है") == "food"
    assert infer_incident_type("district hospital me ration bhejo") == "food"
    assert infer_incident_type("road is blocked with 3 feet waterlogging, traffic stopped") == "info"
    assert infer_incident_type("पानी 3 फीट भर गया है, रास्ता बंद है") == "info"
    assert infer_incident_type("घर डूब गया है, राहत शिविर में जगह चाहिए") == "shelter"
    assert infer_incident_type("shelter ke paas 5 log chat par hain jaldi boat bhejo") == "rescue"
    assert infer_incident_type("need emergency shelter near the boat jetty, ground floor submerged") == "shelter"
    assert infer_incident_type("4 log beghar hain temporary shelter aur tarpaulin chahiye") == "shelter"
    assert infer_incident_type("kutte ne bache ko kaat liya hai") == "animal_attack"
    assert infer_incident_type("hello there") is None


def test_parse_repairs_a_cached_rescue_when_the_words_ask_for_medicine():
    parsed = intake_agent.parse_report(
        "temple road ke paas 2 log bimar hain oxygen aur dawa urgently chahiye.",
        language_hint="hinglish",
    )
    assert parsed.type == IncidentType.MEDICAL


def test_ward_comes_from_the_landmark_in_the_full_report():
    place = "8 log chat par hain pani bohot tezi se badh raha"
    report = "nedumudi boat jetty ke paas 8 log chat par hain pani bohot tezi se badh raha hai"
    assert gazetteer.resolve_ward(place, report) == "ward_3"
    assert gazetteer.resolve_ward("4 मरीज", "चम्पाकुलाम स्कूल के पास 4 मरीजों को दवा चाहिए") == "ward_2"
