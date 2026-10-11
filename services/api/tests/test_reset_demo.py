from fastapi.testclient import TestClient

from app.main import app
from app.tools.storage import storage_service

client = TestClient(app)
AUTH = {"Authorization": "Bearer demo-coordinator-token"}


def test_reset_demo_reloads_kerala_seeds():
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
    assert body["incidents"] >= 1
    assert body["resources"] >= 1
    assert storage_service.get_report("RESET-TEMP") is None
    assert storage_service.get_request("INC-001") is not None


def test_reset_demo_requires_coordinator():
    response = client.post("/api/demo/reset")
    assert response.status_code == 401
