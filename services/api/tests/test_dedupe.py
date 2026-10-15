from app.agents.dedupe import dedupe_agent
from app.agents.intake import intake_agent
from app.models.schemas import IncidentType, HazardType, DedupeDecisionType
from app.models.firestore_models import StoredRequest, RequestStatus
from app.tools.scoring import scoring_engine


def test_hero_case_update_escalates_urgency_and_keeps_history():
    # Initial report: "Gandhi school ke paas 3 log chat par hain"
    initial_extracted = intake_agent.parse_report("Gandhi school ke paas 3 log chat par hain")
    assert initial_extracted.people.count == 3

    req_existing = StoredRequest(
        id="req_gandhi_01",
        type=IncidentType.RESCUE,
        place_text="Gandhi School, Ward 4",
        ward_id="ward_2",
        lat=26.852,
        lng=80.925,
        people_count=3,
        hazard=HazardType.STRANDED,
        status=RequestStatus.NEW,
    )
    initial_score = scoring_engine.compute_urgency(req_existing).score

    # Follow-up hero message: "ab 5 log hain, paani badh raha hai"
    update_text = "ab 5 log hain, paani badh raha hai"
    update_extracted = intake_agent.parse_report(update_text)
    assert update_extracted.people.count == 5

    # Dedupe pre-filter identifies req_gandhi_01 as candidate
    candidates = dedupe_agent.prefilter_candidates(
        new_req=update_extracted,
        new_lat=26.852,
        new_lng=80.925,
        new_ward="ward_2",
        existing_requests=[req_existing]
    )
    assert len(candidates) == 1
    assert candidates[0].id == "req_gandhi_01"

    # Evaluate decision
    decision = dedupe_agent.evaluate(
        raw_text=update_text,
        new_req=update_extracted,
        candidates=candidates,
        new_lat=26.852,
        new_lng=80.925,
        judge=False,
    )

    # Acceptance criteria verification:
    # 1. Decision is UPDATE
    assert decision.decision == DedupeDecisionType.UPDATE
    assert decision.target_request_id == "req_gandhi_01"
    assert "people" in decision.changed_fields
    assert decision.changed_fields["people"]["from"] == 3
    assert decision.changed_fields["people"]["to"] == 5

    # 2. Urgency escalates
    req_existing.people_count = 5
    req_existing.hazard = HazardType.WATER_RISING
    escalated_score = scoring_engine.compute_urgency(req_existing).score
    assert escalated_score > initial_score


def test_hero_case_two_reporters_same_house_becomes_duplicate_with_evidence():
    req_existing = StoredRequest(
        id="req_house_01",
        type=IncidentType.RESCUE,
        place_text="Gandhi High School, Ward 2",
        ward_id="ward_2",
        lat=26.852,
        lng=80.925,
        people_count=4,
        hazard=HazardType.WATER_RISING,
    )

    # Second reporter for same place: "Gandhi school ke paas paani bahut zyada hai madad bhejo"
    second_report_text = "Gandhi school ke paas paani bahut zyada hai madad bhejo"
    second_extracted = intake_agent.parse_report(second_report_text)

    candidates = dedupe_agent.prefilter_candidates(
        new_req=second_extracted,
        new_lat=26.852,
        new_lng=80.925,
        new_ward="ward_2",
        existing_requests=[req_existing]
    )
    assert len(candidates) == 1

    decision = dedupe_agent.evaluate(
        raw_text=second_report_text,
        new_req=second_extracted,
        candidates=candidates
    )

    # Acceptance criteria verification:
    # 1. Decision is DUPLICATE
    assert decision.decision == DedupeDecisionType.DUPLICATE
    assert decision.target_request_id == "req_house_01"
    # 2. Concrete evidence list provided
    assert len(decision.evidence) >= 2
    assert any("landmark" in ev.lower() or "location" in ev.lower() for ev in decision.evidence)


def test_second_candidate_landmark_is_the_duplicate_and_a_different_house_is_not():
    gandhi = StoredRequest(
        id="req_gandhi",
        type=IncidentType.RESCUE,
        place_text="Gandhi High School, Ward 2",
        ward_id="ward_2",
        lat=26.852,
        lng=80.925,
        people_count=4,
        hazard=HazardType.WATER_RISING,
    )
    sangam = StoredRequest(
        id="req_sangam",
        type=IncidentType.RESCUE,
        place_text="Sangam Primary School, Ward 1",
        ward_id="ward_1",
        lat=26.845,
        lng=80.932,
        people_count=3,
        hazard=HazardType.STRANDED,
    )
    text = "Another report from Gandhi High School: roads completely submerged, people on second floor needing help."
    extracted = intake_agent.parse_report(text)
    decision = dedupe_agent.evaluate(text, extracted, [sangam, gandhi])
    assert decision.decision == DedupeDecisionType.DUPLICATE
    assert decision.target_request_id == "req_gandhi"

    other_house = "Different house in Ward 2, House #42: need drinking water for 2 adults."
    other_extracted = intake_agent.parse_report(other_house)
    other = dedupe_agent.evaluate(other_house, other_extracted, [gandhi, sangam])
    assert other.decision == DedupeDecisionType.NEW

