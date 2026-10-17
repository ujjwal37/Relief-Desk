"""An info-only report tells the citizen no team is coming, so no arrival line."""
from fastapi.testclient import TestClient

from app.agents.pipeline import wait_for_idle
from app.main import app
from app.tools.storage import storage_service

client = TestClient(app)


def _submit(text):
    res = client.post("/api/reports", json={"text": text})
    assert res.status_code in (200, 201), res.text
    wait_for_idle(timeout=20)
    return res.json()


def _status(body):
    st = client.get(f"/api/reports/{body['report_id']}/status", params={"token": body["status_token"]})
    assert st.status_code == 200, st.text
    return st.json()


def test_info_closed_report_expects_no_team():
    body = _submit("Synthetic. Nobody stranded at Nedumudi, water level reading only")
    storage_service.close_as_info(body["request_id"])
    data = _status(body)
    assert data["team_expected"] is False
    assert data["eta_minutes"] is None


def test_rescue_report_still_expects_a_team():
    body = _submit("Synthetic. 3 people stranded on a roof at Kainakary, send a boat")
    assert _status(body)["team_expected"] is True
