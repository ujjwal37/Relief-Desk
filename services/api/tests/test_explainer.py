from app.agents.explainer import explainer_agent
from app.models.firestore_models import (
    StoredRequest,
    StoredResource,
    ResourceKind,
    MatchBreakdown,
)
from app.models.schemas import IncidentType


def test_explainer_template_fallback():
    req = StoredRequest(
        id="req_exp_1",
        type=IncidentType.RESCUE,
        lat=26.852,
        lng=80.941,
        people_count=4,
    )
    res = StoredResource(
        id="RES-BOAT-01",
        kind=ResourceKind.BOAT,
        name="Motorized Rescue Boat #01",
        name_hi="मोटर चालित बचाव नाव #01",
        ward_id="ward_3",
        lat=26.852,
        lng=80.941,
        capacity_total=12,
        capacity_remaining=12,
    )
    breakdown = MatchBreakdown(
        distance_km=0.8,
        distance_score=29.0,
        capacity_fit_score=25.0,
        urgency_score=22.5,
        vulnerability_fit_score=15.0,
        total_score=91.5,
    )

    explanation = explainer_agent.explain(req, res, breakdown)
    assert explanation.text_en is not None
    assert len(explanation.text_en) > 10
    assert explanation.text_hi is not None
    # Sentence count is <= 2
    sentences = [s.strip() for s in explanation.text_en.split(". ") if s.strip()]
    assert len(sentences) <= 2


def test_explainer_numeric_consistency_and_forged_output():
    req = StoredRequest(
        id="req_exp_2",
        type=IncidentType.RESCUE,
        lat=26.852,
        lng=80.941,
        people_count=4,
    )
    res = StoredResource(
        id="RES-BOAT-02",
        kind=ResourceKind.BOAT,
        name="Patrol Boat #02",
        ward_id="ward_3",
        lat=26.852,
        lng=80.941,
        capacity_total=10,
        capacity_remaining=10,
    )
    breakdown = MatchBreakdown(
        distance_km=0.8,
        distance_score=29.0,
        capacity_fit_score=25.0,
        urgency_score=20.0,
        vulnerability_fit_score=15.0,
        total_score=89.0,
    )

    # 1. Forged output citing unapproved hallucinated number (e.g. 999 people or 45 km)
    forged_bad = "Patrol Boat #02 has 999 medical kits and is 45 km away from site."
    explanation_bad = explainer_agent.explain(
        req, res, breakdown, forged_llm_text=forged_bad
    )

    # Acceptance criteria: Any number in text not in breakdown triggers fallback!
    assert "999" not in explanation_bad.text_en
    assert "45" not in explanation_bad.text_en
    # Fallback template was activated
    assert "Patrol Boat #02 is 0.8 km away" in explanation_bad.text_en

    # 2. Forged output citing ONLY valid numbers from the breakdown
    forged_good = "Patrol Boat #02 is located 0.8 km away and can rescue 4 people with match score 89.0."
    explanation_good = explainer_agent.explain(
        req, res, breakdown, forged_llm_text=forged_good
    )
    assert explanation_good.text_en == forged_good
