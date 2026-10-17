from pathlib import Path

from fastapi.testclient import TestClient
from app.main import app
from app.config import Settings, settings
from app.api.auth import (
    DEMO_COORDINATOR_EMAIL,
    DEMO_COORDINATOR_TOKEN,
)

client = TestClient(app)


def test_coordinator_endpoint_unauthorized_without_header():
    # Acceptance criteria: Signed-out user cannot call coordinator API (401 test)
    resp = client.get("/api/coordinator/verify")
    assert resp.status_code == 401
    assert "Missing Authorization header" in resp.json()["detail"]


def test_coordinator_endpoint_unauthorized_with_invalid_token():
    resp = client.get(
        "/api/coordinator/verify",
        headers={"Authorization": "Bearer completely-invalid-token"},
    )
    assert resp.status_code == 401
    assert "Invalid or expired coordinator token" in resp.json()["detail"]


def test_coordinator_endpoint_unauthorized_with_bad_scheme():
    resp = client.get(
        "/api/coordinator/verify",
        headers={"Authorization": "Basic dXNlcjpwYXNz"},
    )
    assert resp.status_code == 401
    assert "Bearer scheme" in resp.json()["detail"]


def test_coordinator_endpoint_authorized_with_demo_token():
    resp = client.get(
        "/api/coordinator/verify",
        headers={"Authorization": f"Bearer {DEMO_COORDINATOR_TOKEN}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["authenticated"] is True
    assert data["coordinator"]["email"] == DEMO_COORDINATOR_EMAIL
    assert data["coordinator"]["role"] == "coordinator"


def test_coordinator_login_endpoint_success_and_jwt_verification(monkeypatch):
    monkeypatch.setattr(settings, "COORDINATOR_PASSWORD", "test-coordinator-password")
    login_resp = client.post(
        "/api/auth/login",
        json={"email": DEMO_COORDINATOR_EMAIL, "password": "test-coordinator-password"},
    )
    assert login_resp.status_code == 200
    data = login_resp.json()
    assert data["email"] == DEMO_COORDINATOR_EMAIL
    assert data["role"] == "coordinator"
    jwt_token = data["token"]

    # Verify that the emitted JWT can access coordinator endpoints
    verify_resp = client.get(
        "/api/coordinator/verify",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert verify_resp.status_code == 200
    assert verify_resp.json()["authenticated"] is True


def test_coordinator_login_endpoint_rejection(monkeypatch):
    monkeypatch.setattr(settings, "COORDINATOR_PASSWORD", "")
    bad_resp = client.post(
        "/api/auth/login",
        json={"email": DEMO_COORDINATOR_EMAIL, "password": "WrongPassword123!"},
    )
    assert bad_resp.status_code == 401
    assert "Invalid email or password" in bad_resp.json()["detail"]


def test_coordinator_protected_config_weights():
    # Unauthenticated call to config weights must return 401
    resp_unauth = client.get("/api/config/weights")
    assert resp_unauth.status_code == 401

    # Authenticated call succeeds
    resp_auth = client.get(
        "/api/config/weights",
        headers={"Authorization": f"Bearer {DEMO_COORDINATOR_TOKEN}"},
    )
    assert resp_auth.status_code == 200


def test_demo_login_signs_a_jwt_without_a_password(monkeypatch):
    monkeypatch.setattr(settings, "DEMO_MODE", True)
    resp = client.post("/api/auth/demo-login")
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == DEMO_COORDINATOR_EMAIL
    assert data["role"] == "coordinator"
    assert data["token"] != DEMO_COORDINATOR_TOKEN
    verify = client.get(
        "/api/coordinator/verify",
        headers={"Authorization": f"Bearer {data['token']}"},
    )
    assert verify.status_code == 200
    assert verify.json()["authenticated"] is True


def test_demo_login_off_when_demo_mode_is_false(monkeypatch):
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    resp = client.post("/api/auth/demo-login")
    assert resp.status_code == 403


def test_demo_login_requires_jwt_secret(monkeypatch):
    monkeypatch.setattr(settings, "DEMO_MODE", True)
    monkeypatch.setattr(settings, "JWT_SECRET", "")
    resp = client.post("/api/auth/demo-login")
    assert resp.status_code == 503
    assert "JWT_SECRET" in resp.json()["detail"]


def test_auth_sources_do_not_embed_the_demo_password_or_jwt_default():
    root = Path(__file__).resolve().parents[3]
    auth_py = (root / "services/api/app/api/auth.py").read_text(encoding="utf-8")
    client_ts = (root / "libs/shared/src/lib/services/auth.service.ts").read_text(encoding="utf-8")
    config_py = (root / "services/api/app/config.py").read_text(encoding="utf-8")
    assert "KeralaRelief2026!" not in auth_py
    assert "KeralaRelief2026!" not in client_ts
    assert "relief-desk-coordinator-secret-2026" not in config_py
    assert Settings.model_fields["JWT_SECRET"].default == ""


def test_coordinator_protected_clusters():
    # Unauthenticated call to merge must return 401
    resp_unauth = client.post(
        "/api/requests/req_test/merge",
        json={"secondary_request_id": "req_other"},
    )
    assert resp_unauth.status_code == 401

    # Unauthenticated call to split must return 401
    resp_split_unauth = client.post("/api/requests/req_test/split")
    assert resp_split_unauth.status_code == 401
