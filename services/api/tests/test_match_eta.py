"""Nearby teams are offered first. The demo pack sits within 15 km of Kuttanad."""
from pathlib import Path

import yaml

from app.agents.matching import BOAT_MAX_KM, NEARBY_KM, eta_for_distance, matching_agent
from app.models.firestore_models import ResourceKind, StoredRequest
from app.models.schemas import IncidentType, VulnerableFlags
from app.tools.geo import haversine_distance
from app.tools.storage import storage_service

SEEDS = Path(__file__).resolve().parents[3] / "data" / "synthetic" / "flood_v1" / "seeds.yaml"
RESOURCES = Path(__file__).resolve().parents[3] / "data" / "synthetic" / "flood_v1" / "resources.yaml"


def _eta(km: float, mode: str = "road") -> int:
    return eta_for_distance(km, mode) or max(1, round((km / 20.0) * 60))


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
    assert all(p.breakdown.distance_km <= 25 for p in proposals)  # nothing beyond the 25 km offer limit


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
    assert best.eta_minutes == _eta(best.breakdown.distance_km, "water")
    assert best.eta_minutes < 45


def test_thalavady_rescue_gets_the_local_boat():
    storage_service.load_seed_resources()
    req = StoredRequest(
        id="req_thalavady_rescue",
        type=IncidentType.RESCUE,
        lat=9.362,
        lng=76.518,
        people_count=2,
        urgency_score=70.0,
    )
    proposals = matching_agent.find_matches(req, top_n=5, save_to_storage=False)
    assert proposals
    best = proposals[0]
    assert best.resource_id == "RES-BOAT-05"
    assert best.no_nearby is False
    assert best.breakdown.distance_km < 5
    assert best.eta_minutes == _eta(best.breakdown.distance_km, "water")


def test_a_request_with_no_boat_within_25_km_offers_nothing():
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
    assert proposals == []
    assert BOAT_MAX_KM <= NEARBY_KM


def test_demo_teams_are_within_15_km_of_kuttanad_and_alappuzha():
    seeds = yaml.safe_load(SEEDS.read_text(encoding="utf-8"))
    resources = yaml.safe_load(RESOURCES.read_text(encoding="utf-8"))["resources"]
    wards = {ward["id"]: ward for ward in seeds["wards"]}
    kuttanad = (9.47, 76.39)
    alappuzha = (9.498, 76.339)
    by_kind: dict = {}
    for team in resources:
        by_kind.setdefault(team["kind"], []).append(team)
        if team["id"] in {"RES-MED-04", "RES-MED-06", "RES-BOAT-05", "RES-BOAT-06"}:
            continue  # Southern Kuttanad teams (Thalavady / Edathua) and the Alappuzha medical unit.
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


def test_every_seeded_team_is_inside_the_desk_area():
    """A team 70 km away showed up on Teams as 'No nearby team'. Every loaded team must sit in the desk area."""
    from app.tools.storage import DESK_CENTER
    storage_service.load_seed_resources()
    far = [(r.id, round(haversine_distance(DESK_CENTER[0], DESK_CENTER[1], r.lat, r.lng), 1))
           for r in storage_service._resources.values()
           if haversine_distance(DESK_CENTER[0], DESK_CENTER[1], r.lat, r.lng) > 20]
    assert far == []

