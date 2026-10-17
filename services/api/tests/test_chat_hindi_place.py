from app.agents.chat_intake import ChatIntakeAgent


def test_hindi_place_answer_is_kept_and_location_never_asked_twice():
    agent = ChatIntakeAgent()
    first = agent.process_turn(None, "मदद करो पानी बढ़ रहा है", scenario_id="flood", lang_override="hi")
    assert first.missing_fields[0] == "location"
    sid = first.session_id
    second = agent.process_turn(sid, "नेदुमुडी", scenario_id="flood", lang_override="hi")
    assert "location" not in second.missing_fields
    third = agent.process_turn(sid, "3 लोग", scenario_id="flood", lang_override="hi")
    assert "location" not in third.missing_fields


def test_location_given_up_is_not_asked_again():
    agent = ChatIntakeAgent()
    first = agent.process_turn(None, "help water rising", scenario_id="flood", lang_override="en")
    sid = first.session_id
    agent.process_turn(sid, "asdf", scenario_id="flood", lang_override="en")
    third = agent.process_turn(sid, "4 people", scenario_id="flood", lang_override="en")
    assert "location" not in third.missing_fields
