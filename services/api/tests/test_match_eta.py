"""Nearby teams are offered first. The demo pack sits within 15 km of Kuttanad."""
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


def test_oxygen_case_matches_the_kainakary_clinic():
    storage_service.load_seed_resources()
    req = StoredRequest(
        id="req_oxygen_kainakary",
        type=IncidentType.MEDICAL,
        lat=9.478,
        lng=76.399,
        people_count=3,
        urgency_score=90.0,
        vulnerable=VulnerableFlags(medical_need=True),
    )
    proposals = matching_agent.find_matches(req, top_n=5, save_to_storage=False)
    assert proposals
    best = proposals[0]
    assert best.resource_id == "RES-MED-02"
    assert best.resource_kind == ResourceKind.MEDICAL
    assert best.breakdown.distance_km < 2
    assert best.eta_minutes == _eta(best.breakdown.distance_km)
    assert best.eta_minutes < 15
    assert all(p.breakdown.distance_km <= 15 for p in proposals)


def test_kuttanad_rescue_offers_a_nearby_boat():
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
    best = proposals[0]
    assert best.no_nearby is False
    assert best.breakdown.distance_km < 15
    assert best.eta_minutes == _eta(best.breakdown.distance_km)
    assert best.eta_minutes < 45


def test_chalakudy_rescue_is_outside_the_kuttanad_cluster():
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
    assert best.no_nearby is True
    assert best.breakdown.distance_km > NEARBY_KM
    assert best.eta_minutes is None


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


def test_demo_teams_are_within_15_km_of_kuttanad_and_alappuzha():
    seeds = yaml.safe_load(SEEDS.read_text(encoding="utf-8"))
    resources = yaml.safe_load(RESOURCES.read_text(encoding="utf-8"))["resources"]
    wards = {ward["id"]: ward for ward in seeds["wards"]}
    kuttanad = (9.47, 76.39)
    alappuzha = (9.498, 76.339)
    by_kind: dict = {}
    for team in resources:
        by_kind.setdefault(team["kind"], []).append(team)
        for label, (lat, lng) in (("Kuttanad", kuttanad), ("Alappuzha", alappuzha)):
            km = haversine_distance(lat, lng, team["lat"], team["lng"])
            assert km <= 15, f"{team['id']} is {km:.1f} km from {label}"
    points = [(ward["lat"], ward["lng"]) for ward in wards.values() if ward["district"] == "Alappuzha"]
    assert points
    for kind in ("boat", "medical", "food"):
        for lat, lng in points:
            nearest = min(haversine_distance(lat, lng, team["lat"], team["lng"]) for team in by_kind[kind])
            assert nearest <= 15, f"Alappuzha {kind} is {nearest} km from a ward"
    kind_for = {"rescue": "boat", "medical": "medical", "food": "food", "animal_attack": "medical"}
    for incident in seeds["incidents"]:
        ward = wards.get(incident.get("ward_id"))
        if not ward or ward["district"] != "Alappuzha":
            continue
        kind = kind_for.get(incident["type"])
        if not kind:
            continue
        nearest = min(
            haversine_distance(incident["lat"], incident["lng"], team["lat"], team["lng"])
            for team in by_kind[kind]
        )
        assert nearest <= 15, f"{incident['id']} {kind} is {nearest} km"
