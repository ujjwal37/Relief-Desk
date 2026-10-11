import pytest
from pydantic import ValidationError
from app.models.schemas import (
    IncidentType,
    HazardType,
    UrgencyHint,
    SupportedLanguage,
    DedupeDecisionType,
    ExtractedRequest,
    DedupeDecision,
    Explanation,
    PeopleInfo,
    VulnerableFlags,
)


def test_extracted_request_valid():
    req = ExtractedRequest(
        type=IncidentType.RESCUE,
        place_text="Gandhi School, Ward 4",
        people=PeopleInfo(count=5, confidence=0.95),
        vulnerable=VulnerableFlags(child=True, elderly=True),
        hazard=HazardType.WATER_RISING,
        urgency_hint=UrgencyHint.HIGH,
        language=SupportedLanguage.HINGLISH,
        evidence_spans={"people": "5 log", "vulnerable": "bache aur buzurg"},
    )
    assert req.type == IncidentType.RESCUE
    assert req.people.count == 5
    assert req.vulnerable.child is True
    assert req.vulnerable.elderly is True


def test_extracted_request_rejects_bad_enum():
    with pytest.raises(ValidationError):
        ExtractedRequest(type="unsupported_disaster_type")


def test_extracted_request_rejects_invalid_count():
    with pytest.raises(ValidationError):
        ExtractedRequest(people=PeopleInfo(count=-5))

    with pytest.raises(ValidationError):
        ExtractedRequest(people=PeopleInfo(count=99999))


def test_evidence_span_validation():
    req = ExtractedRequest(
        evidence_spans={"people": "forged_span_not_in_text"}
    )
    req.validate_spans_against_raw("Paani bahut zyada hai, madad chahiye")
    assert req.confidence.people == 0.0
    assert req.needs_human_review is True


def test_dedupe_decision_valid():
    decision = DedupeDecision(
        decision=DedupeDecisionType.UPDATE,
        target_request_id="req-123",
        changed_fields={"people": {"from": 3, "to": 5}},
        evidence=["People count increased from 3 to 5", "Same phone hash"],
        confidence=0.9
    )
    assert decision.decision == DedupeDecisionType.UPDATE
    assert decision.target_request_id == "req-123"


def test_dedupe_decision_rejects_update_without_changed_fields():
    with pytest.raises(ValidationError):
        DedupeDecision(
            decision=DedupeDecisionType.UPDATE,
            target_request_id="req-123",
            changed_fields={},
        )


def test_dedupe_decision_rejects_duplicate_without_target_id():
    with pytest.raises(ValidationError):
        DedupeDecision(
            decision=DedupeDecisionType.DUPLICATE,
            target_request_id=None,
        )


def test_explanation_numeric_consistency():
    explanation = Explanation(
        text_en="Matched boat B1 located 1.5 km away with 6 available seats.",
        text_hi="नाव B1 1.5 किमी दूर उपलब्ध है।"
    )
    # Allowed numbers contains 1.5 and 6
    assert explanation.verify_numeric_consistency([1.5, 6, 10]) is True

    # Hallucinated number 99 not in allowed list
    hallucinated = Explanation(
        text_en="Matched boat with 99 available seats.",
    )
    assert hallucinated.verify_numeric_consistency([1.5, 6]) is False
