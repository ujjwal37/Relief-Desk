"""Dog-attack pack is config and synthetic seeds only. No scenario branch."""

from app.main import app
from app.tools.scenario_loader import scenario_registry
from app.tools.storage import storage_service
from fastapi.testclient import TestClient

client = TestClient(app)
AUTH = {"Authorization": "Bearer demo-coordinator-token"}


def test_dog_pack_is_config_and_fixed_first_aid():
    dog = scenario_registry.get_scenario("dog_attack")
    assert dog is not None
    assert dog.id == "dog_attack"
    assert "dog_bite_first_aid" in dog.safety_line_ids
    line = scenario_registry.get_safety_line("dog_bite_first_aid", lang="en")
    assert "15 minutes" in line
    assert "hospital" in line.lower()
    assert "mg" not in line.lower()


def test_dog_seeds_and_pack_filter():
    listed = client.get("/api/scenarios")
    assert listed.status_code == 200
    assert any(row["id"] == "dog_attack" for row in listed.json())

    dogs = [req for req in storage_service.list_requests() if req.id.startswith("DOG-")]
    assert len(dogs) >= 4
    assert all(req.pack_id == "dog_attack" for req in dogs)

    filtered = client.get("/api/requests?pack_id=dog_attack", headers=AUTH)
    assert filtered.status_code == 200
    rows = filtered.json()
    assert rows
    assert all(row["id"].startswith("DOG-") for row in rows)
    assert all(row["pack_id"] == "dog_attack" for row in rows)

    flood = client.get("/api/requests?pack_id=flood", headers=AUTH)
    assert flood.status_code == 200
    assert all(not row["id"].startswith("DOG-") for row in flood.json())
