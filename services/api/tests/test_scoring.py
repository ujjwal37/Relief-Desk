from fastapi.testclient import TestClient
from app.main import app
from app.models.firestore_models import StoredRequest, RequestStatus
from app.models.schemas import IncidentType, HazardType, VulnerableFlags
from app.tools.scoring import ScoringEngine, UrgencyWeights
from app.tools.storage import storage_service

client = TestClient(app)


def test_child_plus_elderly_outranks_same_size_adult_case():
    scoring = ScoringEngine()

    # Case A: 5 people, all adults, no vulnerable flags
    adult_req = StoredRequest(
        id="req_adults",
        type=IncidentType.RESCUE,
        hazard=HazardType.WATER_RISING,
        people_count=5,
        vulnerable=VulnerableFlags(child=False, elderly=False),
    )

    # Case B: 5 people, child + elderly present
    vuln_req = StoredRequest(
        id="req_vuln",
        type=IncidentType.RESCUE,
        hazard=HazardType.WATER_RISING,
        people_count=5,
        vulnerable=VulnerableFlags(child=True, elderly=True),
    )

    res_adult = scoring.compute_urgency(adult_req)
    res_vuln = scoring.compute_urgency(vuln_req)

    # Acceptance criteria: child+elderly outranks same-size adult case
    assert res_vuln.score > res_adult.score
    # Reason string is produced
    assert "vulnerable: child, elderly" in res_vuln.reason
    assert "water rising" in res_vuln.reason


def test_changing_weights_changes_rank():
    scoring = ScoringEngine()

    # Request 1: 1 person, highly vulnerable (pregnant + medical need), low hazard
    req1 = StoredRequest(
        id="req_single_vuln",
        people_count=1,
        hazard=HazardType.NONE,
        vulnerable=VulnerableFlags(pregnant=True, medical_need=True),
    )

    # Request 2: 25 people, no vulnerable flags, water rising
    req2 = StoredRequest(
        id="req_crowd",
        people_count=25,
        hazard=HazardType.WATER_RISING,
        vulnerable=VulnerableFlags(),
    )

    # With default weights (vulnerability weight 0.35, people weight 0.25)
    r1_default = scoring.compute_urgency(req1)
    r2_default = scoring.compute_urgency(req2)

    # Now coordinator adjusts weights: heavy focus on people count, minimal on vulnerability
    custom = UrgencyWeights(
        w_vulnerability=0.05,
        w_people=0.70,
        w_hazard=0.15,
        w_wait_time=0.10,
    )
    r1_crowd_boost = scoring.compute_urgency(req1, custom_weights=custom)
    r2_crowd_boost = scoring.compute_urgency(req2, custom_weights=custom)

    # Acceptance criteria: changing weight changes rank
    assert r2_crowd_boost.score > r1_crowd_boost.score


def test_weights_api_endpoint_and_audit():
    auth_headers = {"Authorization": "Bearer demo-coordinator-token"}
    # Read current weights
    get_resp = client.get("/api/config/weights", headers=auth_headers)
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert "w_vulnerability" in data

    # Update weights
    payload = {
        "version": data["version"],
        "w_vulnerability": 0.40,
        "w_people": 0.20,
        "w_hazard": 0.25,
        "w_wait_time": 0.15,
        "confidence_discount_factor": 0.20,
        "v_child": 1.1,
        "v_elderly": 1.1,
        "v_disabled": 1.0,
        "v_pregnant": 1.3,
        "v_medical": 1.3,
    }
    put_resp = client.put("/api/config/weights", json=payload, headers=auth_headers)
    assert put_resp.status_code == 200
    updated = put_resp.json()
    assert updated["w_vulnerability"] == 0.40
    assert updated["version"] == data["version"] + 1

    # Audit log recorded
    trail = storage_service.get_audit_trail(target="config/weights")
    assert len(trail) >= 1
    assert trail[-1].action == "weights_updated"
    # Later tests score the seed pack with the desk defaults.
    from app.tools.scoring import UrgencyWeights, scoring_engine
    scoring_engine.update_weights(UrgencyWeights())


def test_adults_on_roof_with_window_water_or_boat_are_urgent():
    scoring = ScoringEngine()
    cases = [
        "two people on the roof, water at window level, need a boat",
        "छत पर दो लोग फंसे हैं, खिड़की तक पानी है, नाव भेजिए",
        "do log chhat par hain, paani khidki tak aa gaya, naav bhejo",
    ]
    for text in cases:
        req = StoredRequest(
            id="req_roof_boat",
            type=IncidentType.RESCUE,
            hazard=HazardType.UNKNOWN,
            people_count=2,
            vulnerable=VulnerableFlags(),
            raw_text=text,
        )
        result = scoring.compute_urgency(req)
        assert result.tier == "urgent", text
        assert result.score >= 60.0, (text, result.score, result.reason)
