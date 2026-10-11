import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
AUTH = {"Authorization": "Bearer demo-coordinator-token"}
RESULTS = Path(__file__).resolve().parents[3] / "bench" / "results" / "latest.json"


def test_benchmark_endpoint_equals_latest_json():
    denied = client.get("/api/benchmark/latest")
    assert denied.status_code == 401
    response = client.get("/api/benchmark/latest", headers=AUTH)
    assert response.status_code == 200
    assert response.json() == json.loads(RESULTS.read_text(encoding="utf-8"))
