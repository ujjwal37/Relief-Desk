"""The ADK graph is Intake, then Dedupe and Triage together, then Matching, then Explainer."""
import uuid

from fastapi.testclient import TestClient
from google.adk.agents import LlmAgent, ParallelAgent, SequentialAgent

from app.agents.pipeline import PIPELINE, check_capacity, score_urgency
from app.main import app
from app.tools.storage import storage_service

client = TestClient(app)
AUTH = {"Authorization": "Bearer demo-coordinator-token"}


def test_pipeline_shape_and_output_keys():
    assert isinstance(PIPELINE, SequentialAgent)
    names = [agent.name for agent in PIPELINE.sub_agents]
    assert names == ["Intake", "DedupeAndTriage", "Matching", "Explainer"]
    parallel = PIPELINE.sub_agents[1]
    assert isinstance(parallel, ParallelAgent)
    assert [agent.name for agent in parallel.sub_agents] == ["Dedupe", "Triage"]
    keys = {agent.name: agent.output_key for agent in PIPELINE.sub_agents if isinstance(agent, LlmAgent)}
    keys.update({agent.name: agent.output_key for agent in parallel.sub_agents})
    assert keys["Intake"] == "intake"
    assert keys["Dedupe"] == "dedupe"
    assert keys["Triage"] == "triage"
    assert keys["Matching"] == "matching"
    assert keys["Explainer"] == "explainer"
    assert any(tool.name == "score_urgency" for tool in PIPELINE.sub_agents[1].sub_agents[1].tools)
    assert any(tool.name == "check_capacity" for tool in PIPELINE.sub_agents[2].tools)


def test_urgency_tool_matches_the_scoring_engine_and_does_not_dispatch():
    from app.models.firestore_models import StoredRequest
    from app.tools.scoring import scoring_engine

    mirror = StoredRequest(id="mirror", type="rescue", people_count=4)
    mirror.vulnerable.child = True
    scored = score_urgency(4, "rescue", child=True)
    assert scored["score"] == scoring_engine.compute_urgency(mirror).score
    before = check_capacity("boat")["available"]
    score_urgency(8, "rescue", elderly=True)
    assert check_capacity("boat")["available"] == before
    assert check_capacity("boat")["dispatched"] is False


def test_submit_shows_analysing_then_completes(monkeypatch):
    held = []
    monkeypatch.setattr("app.agents.pipeline._spawn", lambda fn: held.append(fn))
    # reports imports spawn_analysis which calls spawn(), which reads _spawn at call time.
    token = uuid.uuid4().hex[:8]
    created = client.post(
        "/api/reports",
        json={
            "text": f"4 people stranded near {token} jetty, send a boat",
            "lang": "en",
            "channel": "text",
            "location_pin": {"lat": 8.2, "lng": 77.2},
            "idempotency_key": f"pipe-{token}",
        },
    )
    assert created.status_code == 200, created.text
    request_id = created.json()["request_id"]
    stored = storage_service.get_request(request_id)
    assert stored is not None
    assert stored.analysis_status == "analysing"
    assert held, "analysis should be queued, not finished inside the request"
    held[0]()
    done = storage_service.get_request(request_id)
    assert done.analysis_status == "complete"
    assert done.analysis["matching"]["dispatched"] is False
    assert "not medical or legal advice" in done.analysis["explainer"]
    assert done.status.value == "new"
    listed = client.get("/api/requests", headers=AUTH)
    card = next(row for row in listed.json() if row["id"] == request_id)
    assert card["analysis_status"] == "complete"
