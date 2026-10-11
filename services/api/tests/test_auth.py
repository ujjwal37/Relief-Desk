import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.api.auth import (
    DEMO_COORDINATOR_EMAIL,
    DEMO_COORDINATOR_PASSWORD,
    DEMO_COORDINATOR_TOKEN,
    create_coordinator_token,
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


def test_coordinator_login_endpoint_success_and_jwt_verification():
    # Login with seeded synthetic credentials
    login_resp = client.post(
        "/api/auth/login",
        json={"email": DEMO_COORDINATOR_EMAIL, "password": DEMO_COORDINATOR_PASSWORD},
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


def test_coordinator_login_endpoint_rejection():
    # Invalid password test
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
