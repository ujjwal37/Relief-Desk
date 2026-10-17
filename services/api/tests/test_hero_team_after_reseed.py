"""The hero case always has its team after a fresh seed, and the seed stays in Kuttanad."""
from app.agents.matching import matching_agent
from app.tools.storage import EXCLUDED_SEED_WARDS, storage_service


def test_hero_has_a_team_after_full_reseed():
    for _ in range(2):  # reseed twice: the second load must not lose the team
        storage_service.load_full_scenario()
        hero = storage_service.get_request("INC-001")
        assert hero is not None
        proposals = matching_agent.find_matches(hero, top_n=3, save_to_storage=False)
        assert proposals, "hero INC-001 lost its team"
        assert proposals[0].breakdown.distance_km < 2.0


def test_seed_is_kuttanad_only():
    for req in storage_service.list_requests():
        if (req.id or "").startswith("INC-"):
            assert req.ward_id not in EXCLUDED_SEED_WARDS, (req.id, req.ward_id)
    for res in storage_service.list_resources():
        assert res.ward_id not in EXCLUDED_SEED_WARDS, (res.id, res.ward_id)
