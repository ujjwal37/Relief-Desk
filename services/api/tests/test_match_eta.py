"""Nearby teams are offered first. Past 30 km the card says there is no nearby team."""
from pathlib import Path

import yaml

from app.agents.matching import NEARBY_KM, matching_agent
from app.models.firestore_models import ResourceKind, StoredRequest
from app.models.schemas import IncidentType, VulnerableFlags
from app.tools.geo import haversine_distance
from app.tools.storage import storage_service

SEEDS = Path(__file__).resolve().parents[3] / "data" / "synthetic" / "flood_v1" / "seeds.yaml"
RESOURCES = Path(__file__).resolve().parents[3] / "data" / "synthetic" / "flood_v1" / "resources.yaml"


def _eta(km: float) -> int:
    return max(1, round((km / 20.0) * 60))


def test_oxygen_case_matches_the_varapuzha_clinic():
    storage_service.load_seed_resources()
    req = StoredRequest(
        id="req_oxygen_varapuzha",
        type=IncidentType.MEDICAL,
        lat=10.07985,
        lng=76.27371,
        people_count=3,
        urgency_score=90.0,
        vulnerable=VulnerableFlags(medical_need=True),
    )
    proposals = matching_agent.find_matches(req, top_n=5, save_to_storage=False)
    assert proposals
    best = proposals[0]
    assert best.resource_id == "RES-MED-04"
    assert best.resource_kind == ResourceKind.MEDICAL
    assert best.breakdown.distance_km < 2
    assert best.eta_minutes == _eta(best.breakdown.distance_km)
    assert best.eta_minutes < 15
    assert all(p.breakdown.distance_km <= 40 for p in proposals)


def test_alappuzha_rescue_does_not_offer_the_wayanad_boat():
    storage_service.load_seed_resources()
    req = StoredRequest(
        id="req_alappuzha_rescue",
        type=IncidentType.RESCUE,
        lat=9.436,
        lng=76.398,
        people_count=4,
        urgency_score=80.0,
    )
    proposals = matching_agent.find_matches(req, top_n=5, save_to_storage=False)
    assert proposals
    assert all(p.resource_id != "RES-BOAT-04" for p in proposals)
    assert proposals[0].breakdown.distance_km < 5
    assert proposals[0].eta_minutes == _eta(proposals[0].breakdown.distance_km)
    assert proposals[0].eta_minutes < 20


def test_chalakudy_rescue_has_a_nearby_thrissur_boat():
    storage_service.load_seed_resources()
    req = StoredRequest(
        id="req_chalakudy_rescue",
        type=IncidentType.RESCUE,
        lat=10.303,
        lng=76.335,
        people_count=2,
        urgency_score=70.0,
    )
    proposals = matching_agent.find_matches(req, top_n=5, save_to_storage=False)
    assert proposals
    best = proposals[0]
    assert best.resource_id == "RES-BOAT-03"
    assert best.no_nearby is False
    assert best.breakdown.distance_km <= NEARBY_KM
    assert best.eta_minutes == _eta(best.breakdown.distance_km)
    assert best.eta_minutes < 90


def test_a_request_with_no_team_within_30_km_hides_the_minute_eta():
    storage_service.load_seed_resources()
    req = StoredRequest(
        id="req_far_cluster",
        type=IncidentType.RESCUE,
        lat=26.852,
        lng=80.940,
        people_count=4,
        urgency_score=80.0,
    )
    proposals = matching_agent.find_matches(req, top_n=5, save_to_storage=False)
    assert len(proposals) >= 2
    assert all(p.breakdown.distance_km > NEARBY_KM for p in proposals)
    assert all(p.no_nearby for p in proposals)
    assert all(p.eta_minutes is None for p in proposals)


def test_each_district_has_a_boat_medical_and_food_team_near_its_cases():
    seeds = yaml.safe_load(SEEDS.read_text())
    resources = yaml.safe_load(RESOURCES.read_text())["resources"]
    wards = {ward["id"]: ward for ward in seeds["wards"]}
    by_kind: dict = {}
    for team in resources:
        by_kind.setdefault(team["kind"], []).append(team)
    for district in ("Alappuzha", "Ernakulam", "Thrissur", "Wayanad"):
        points = [(ward["lat"], ward["lng"]) for ward in wards.values() if ward["district"] == district]
        assert points, district
        for kind in ("boat", "medical", "food"):
            for lat, lng in points:
                nearest = min(
                    haversine_distance(lat, lng, team["lat"], team["lng"]) for team in by_kind[kind]
                )
                assert nearest <= NEARBY_KM, f"{district} {kind} is {nearest} km from a ward"
    kind_for = {"rescue": "boat", "medical": "medical", "food": "food", "animal_attack": "medical"}
    for incident in seeds["incidents"]:
        kind = kind_for.get(incident["type"])
        if not kind:
            continue
        nearest = min(
            haversine_distance(incident["lat"], incident["lng"], team["lat"], team["lng"])
            for team in by_kind[kind]
        )
        assert nearest <= NEARBY_KM, f"{incident['id']} {kind} is {nearest} km"
