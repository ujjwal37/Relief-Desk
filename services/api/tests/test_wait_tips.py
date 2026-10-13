from app.models.firestore_models import IncidentType, StoredRequest
from app.tools.wait_tips import DOG, FOOD, MEDICAL, RESCUE, SHELTER, DEFAULT, tips_for_request, wait_tips_for


def test_type_to_tips_mapping():
    assert wait_tips_for("rescue") == list(RESCUE)
    assert wait_tips_for("flood") == list(RESCUE)
    assert wait_tips_for("water_rising") == list(RESCUE)
    assert wait_tips_for("medical") == list(MEDICAL)
    assert wait_tips_for("food") == list(FOOD)
    assert wait_tips_for("food_water") == list(FOOD)
    assert wait_tips_for("shelter") == list(SHELTER)
    assert wait_tips_for("animal_attack") == list(DOG)
    assert wait_tips_for("dog_attack") == list(DOG)
    assert wait_tips_for("info") == list(DEFAULT)
    assert wait_tips_for(None) == list(DEFAULT)
    assert wait_tips_for("") == list(DEFAULT)
    for tips in (RESCUE, MEDICAL, FOOD, SHELTER, DOG, DEFAULT):
        assert len(tips) == 3
        assert all(tip.startswith("status.tip") for tip in tips)


def test_picked_type_applies_until_classification_finishes():
    waiting = StoredRequest(
        id="req_waiting",
        type=IncidentType.RESCUE,
        analysis_status="analysing",
        picked_type="medical",
    )
    assert tips_for_request(waiting) == list(MEDICAL)

    classified = StoredRequest(
        id="req_classified",
        type=IncidentType.SHELTER,
        analysis_status="complete",
        picked_type="medical",
    )
    assert tips_for_request(classified) == list(SHELTER)

    free_text = StoredRequest(id="req_free", type=IncidentType.FOOD, analysis_status="analysing")
    assert tips_for_request(free_text) == list(FOOD)
