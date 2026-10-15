"""The running demo starts small. The full flood pack stays behind DEMO_SEED=full and the button."""
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from app.main import app
from app.tools.geo import haversine_distance
from app.config import settings
from app.tools.demo_cases import DEMO_CASES, DEMO_TEAM_IDS
from app.tools.storage import SMALL_CASE_IDS, SMALL_TEAM_IDS, active_seed_mode, storage_service

ROOT = Path(__file__).resolve().parents[3]
# Kuttanad / Alappuzha pin used when a phone has no finer fix.
ALAPPUZHA = (9.498, 76.339)

client = TestClient(app)
AUTH = {"Authorization": "Bearer demo-coordinator-token"}


def _restore_full():
    storage_service.load_full_scenario()


def test_reset_returns_two_cases_and_full_reloads_the_pack():
    try:
        reset = client.post("/api/demo/reset", headers=AUTH)
        assert reset.status_code == 200
        body = reset.json()
        assert body["seed"] == "small"
        demo_ids = {row["id"] for row in DEMO_CASES} if settings.DEMO_MODE else set()
        extra_teams = {tid for tid in DEMO_TEAM_IDS if tid not in SMALL_TEAM_IDS} if settings.DEMO_MODE else set()
        assert body["incidents"] == len(SMALL_CASE_IDS) + len(demo_ids)
        assert body["resources"] == len(SMALL_TEAM_IDS) + len(extra_teams)
        ids = {row["id"] for row in client.get("/api/requests", headers=AUTH).json()}
        assert ids == set(SMALL_CASE_IDS) | demo_ids
        teams = {row["id"] for row in client.get("/api/resources", headers=AUTH).json()}
        assert teams == set(SMALL_TEAM_IDS) | extra_teams

        full = client.post("/api/demo/full", headers=AUTH)
        assert full.status_code == 200
        assert full.json()["seed"] == "full"
        assert full.json()["incidents"] >= 40
        again = {row["id"] for row in client.get("/api/requests", headers=AUTH).json()}
        assert "INC-040" in again
        assert len(again) >= 40

        back = client.post("/api/demo/reset", headers=AUTH)
        assert back.json()["seed"] == "small"
        after = {row["id"] for row in client.get("/api/requests", headers=AUTH).json()}
        assert after == set(SMALL_CASE_IDS) | demo_ids
    finally:
        _restore_full()


def test_small_demo_teams_are_within_15_km_of_kuttanad():
    seeds = yaml.safe_load((ROOT / "data/synthetic/flood_v1/seeds.yaml").read_text(encoding="utf-8"))
    resources = yaml.safe_load((ROOT / "data/synthetic/flood_v1/resources.yaml").read_text(encoding="utf-8"))
    cases = [row for row in seeds["incidents"] if row["id"] in SMALL_CASE_IDS]
    teams = [row for row in resources["resources"] if row["id"] in SMALL_TEAM_IDS]
    assert len(cases) == len(SMALL_CASE_IDS)
    assert len(teams) == len(SMALL_TEAM_IDS)
    points = [(row["lat"], row["lng"]) for row in cases] + [ALAPPUZHA]
    for team in teams:
        for lat, lng in points:
            km = haversine_distance(lat, lng, team["lat"], team["lng"])
            assert km <= 15, f"{team['id']} is {km:.1f} km from {(lat, lng)}"


def test_pytest_keeps_the_full_pack_unless_demo_seed_is_set(monkeypatch):
    monkeypatch.delenv("DEMO_SEED", raising=False)
    assert active_seed_mode() == "full"
    monkeypatch.setenv("DEMO_SEED", "small")
    assert active_seed_mode() == "small"
    monkeypatch.setenv("DEMO_SEED", "full")
    assert active_seed_mode() == "full"
