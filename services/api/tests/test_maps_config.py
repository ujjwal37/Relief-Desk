from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

client = TestClient(app)


def test_maps_config_is_off_for_placeholder_key(monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_MAPS_API_KEY", "replace-me")
    response = client.get("/api/config/maps")
    assert response.status_code == 200
    assert response.json() == {"enabled": False, "apiKey": None, "mapId": "DEMO_MAP_ID"}


def test_maps_config_returns_browser_key_when_set(monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_MAPS_API_KEY", "test-browser-key-not-secret")
    response = client.get("/api/config/maps")
    assert response.status_code == 200
    assert response.json() == {"enabled": True, "apiKey": "test-browser-key-not-secret", "mapId": "DEMO_MAP_ID"}


def test_maps_config_returns_configured_map_id(monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_MAPS_API_KEY", "replace-me")
    monkeypatch.setattr(settings, "GOOGLE_MAPS_MAP_ID", "relief-desk-muted")
    response = client.get("/api/config/maps")
    assert response.status_code == 200
    assert response.json()["mapId"] == "relief-desk-muted"
    assert response.json()["enabled"] is False
