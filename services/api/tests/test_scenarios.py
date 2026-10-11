import tempfile
from pathlib import Path
import yaml
from fastapi.testclient import TestClient
from app.main import app
from app.tools.scenario_loader import ScenarioRegistry, scenario_registry


client = TestClient(app)


def test_flood_scenario_loaded():
    flood = scenario_registry.get_scenario("flood")
    assert flood is not None
    assert flood.id == "flood"
    assert "rescue" in flood.incident_types
    assert len(flood.tiles) >= 4
    assert "location" in flood.follow_up_questions
    assert "people_count" in flood.follow_up_questions
    assert "call_112" in flood.safety_line_ids


def test_safety_line_retrieval():
    call_112_en = scenario_registry.get_safety_line("call_112", lang="en")
    assert "112" in call_112_en
    call_112_hi = scenario_registry.get_safety_line("call_112", lang="hi")
    assert "112" in call_112_hi


def test_dynamic_scenario_addition_without_code_changes():
    # Test acceptance criteria: adding a dummy fire.yaml makes a new tile + questions appear with zero code change
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        fire_yaml = tmp_path / "fire.yaml"
        dummy_content = {
            "id": "fire",
            "title": "Urban Fire Emergency",
            "incident_types": ["fire_rescue", "burn_injury"],
            "tiles": [
                {
                    "id": "trapped_fire",
                    "label_en": "Trapped by Flames",
                    "label_hi": "आग में फंसे हैं",
                    "incident_type": "fire_rescue",
                    "icon": "flame"
                }
            ],
            "follow_up_questions": {
                "floor_level": {
                    "en": "Which floor are you on?",
                    "hi": "आप किस मंजिल पर हैं?",
                    "hinglish": "Aap kis floor par hain?"
                }
            },
            "urgency_rules": {"smoke_inhalation_boost": 40},
            "resource_types": ["fire_truck", "ambulance"],
            "safety_line_ids": ["call_112"]
        }
        with open(fire_yaml, "w", encoding="utf-8") as f:
            yaml.dump(dummy_content, f)

        custom_registry = ScenarioRegistry(scenarios_dir=tmp_path)
        fire_scenario = custom_registry.get_scenario("fire")
        assert fire_scenario is not None
        assert fire_scenario.id == "fire"
        assert len(fire_scenario.tiles) == 1
        assert fire_scenario.tiles[0].label_en == "Trapped by Flames"
        assert "floor_level" in fire_scenario.follow_up_questions


def test_scenarios_api_endpoints():
    response = client.get("/api/scenarios")
    assert response.status_code == 200
    scenarios = response.json()
    assert any(s["id"] == "flood" for s in scenarios)

    flood_resp = client.get("/api/scenarios/flood")
    assert flood_resp.status_code == 200
    data = flood_resp.json()
    assert data["id"] == "flood"
    assert len(data["tiles"]) >= 4

    missing = client.get("/api/scenarios/non_existent_pack")
    assert missing.status_code == 404
