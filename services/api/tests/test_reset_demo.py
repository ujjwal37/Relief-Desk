from fastapi.testclient import TestClient

from app.main import app
from app.tools.storage import storage_service

client = TestClient(app)
AUTH = {"Authorization": "Bearer demo-coordinator-token"}


def _restore_full():
    storage_service.load_full_scenario()


def test_reset_demo_reloads_kerala_seeds():
    try:
        _reset_reloads_kerala_seeds()
    finally:
        _restore_full()


def _reset_reloads_kerala_seeds():
    storage_service.save_report_raw(
        raw_text="temporary synthetic note that reset must drop",
        channel="text",
        lang="en",
        source_id="reset-test",
        trust_level="anonymous",
        pack_id="flood",
        report_id="RESET-TEMP",
    )
    assert storage_service.get_report("RESET-TEMP") is not None

    response = client.post("/api/demo/reset", headers=AUTH)
    assert response.status_code == 200
    body = response.json()
    assert body["seed"] == "small"
    assert body["incidents"] == 2
    assert body["resources"] >= 1
    assert storage_service.get_report("RESET-TEMP") is None
    assert storage_service.get_request("INC-001") is not None


def test_reset_demo_requires_coordinator():
    response = client.post("/api/demo/reset")
    assert response.status_code == 401


def test_reset_works_for_demo_coordinator_with_demo_mode_off(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "DEMO_MODE", False)
    try:
        assert client.post("/api/demo/reset", headers=AUTH).status_code == 200
    finally:
        _restore_full()


def test_reset_refused_for_other_coordinator_with_demo_mode_off(monkeypatch):
    from app.api.auth import CoordinatorUser, get_current_coordinator
    from app.config import settings

    monkeypatch.setattr(settings, "DEMO_MODE", False)
    app.dependency_overrides[get_current_coordinator] = lambda: CoordinatorUser(
        uid="u2", email="real-coordinator@example.org", role="coordinator")
    try:
        assert client.post("/api/demo/reset").status_code == 403
    finally:
        app.dependency_overrides.clear()
