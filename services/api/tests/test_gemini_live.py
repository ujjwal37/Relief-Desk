"""Live Gemini is used only when the key is set and demo mode is off. The client is mocked."""
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from app.agents.chat_intake import chat_intake_agent
from app.agents.dedupe import dedupe_agent
from app.agents.explainer import explainer_agent
from app.agents.intake import intake_agent
from app.config import settings
from app.llm.client import llm_client
from app.main import app
from app.models.firestore_models import MatchBreakdown, ResourceKind, StoredRequest, StoredResource
from app.models.schemas import ExtractedRequest, IncidentType, PeopleInfo

client = TestClient(app)
AUTH = {"Authorization": "Bearer demo-coordinator-token"}


def _intake_json(incident_type: str, note: str) -> str:
    return json.dumps(
        {
            "type": incident_type,
            "place_text": "Aluva",
            "people": {"count": 2, "confidence": 0.9},
            "vulnerable": {
                "child": False,
                "elderly": False,
                "disabled": False,
                "pregnant": False,
                "medical_need": False,
            },
            "hazard": "none",
            "urgency_hint": "medium",
            "language": "en",
            "is_update_phrase": False,
            "confidence": {
                "type": 0.91,
                "place": 0.8,
                "people": 0.8,
                "vulnerable": 0.7,
                "urgency": 0.7,
            },
            "evidence_spans": {},
            "notes": note,
        }
    )


@pytest.fixture
def live_gemini(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    monkeypatch.setattr(settings, "GEMINI_ENABLED", True)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key-not-a-secret")
    monkeypatch.setattr("app.llm.client.CACHE_DIR", tmp_path)
    llm_client._memory_cache.clear()
    llm_client._memory_source.clear()
    llm_client.last_source = "offline_fallback"
    yield
    llm_client._memory_cache.clear()
    llm_client._memory_source.clear()


def test_placeholder_key_and_demo_mode_are_not_live(monkeypatch):
    monkeypatch.setattr(settings, "DEMO_MODE", True)
    monkeypatch.setattr(settings, "GEMINI_ENABLED", True)
    monkeypatch.setattr(settings, "AI_MODE", "auto")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key-not-a-secret")
    assert llm_client.gemini_live() is True
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "replace-me")
    assert llm_client.gemini_live() is False
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key-not-a-secret")
    monkeypatch.setattr(settings, "GEMINI_ENABLED", False)
    assert llm_client.gemini_live() is False


def test_intake_uses_the_mocked_gemini_reply(live_gemini, monkeypatch):
    calls = {"n": 0}

    def fake_call(system, user, timeout_s=12.0):
        calls["n"] += 1
        return _intake_json("food", "from-gemini")

    monkeypatch.setattr(llm_client, "_call_gemini", fake_call)
    text = f"ZXFOOD{uuid.uuid4().hex[:8]} waiting beside the old tree"
    extracted = intake_agent.parse_report(text, language_hint="en")
    assert calls["n"] == 1
    assert extracted.type == IncidentType.FOOD
    assert extracted.notes == "from-gemini"
    assert llm_client.last_source == "gemini"
    assert llm_client.last_ai.provider == "gemini"
    assert llm_client.last_ai.model == settings.GEMINI_MODEL
    assert llm_client.last_ai.cached is False
    assert llm_client.last_ai.fallback_reason is None


def test_timeout_and_error_use_the_offline_fallback(live_gemini, monkeypatch):
    def boom(system, user, timeout_s=12.0):
        raise TimeoutError("Gemini timed out")

    monkeypatch.setattr(llm_client, "_call_gemini", boom)
    extracted = intake_agent.parse_report(f"ZXTO{uuid.uuid4().hex[:8]} five people stranded")
    assert llm_client.last_source == "offline_fallback"
    assert extracted.people.count == 5

    def explode(system, user, timeout_s=12.0):
        raise RuntimeError("sdk down")

    monkeypatch.setattr(llm_client, "_call_gemini", explode)
    intake_agent.parse_report(f"ZXERR{uuid.uuid4().hex[:8]} three people need a boat")
    assert llm_client.last_source == "offline_fallback"


def test_demo_mode_does_not_call_gemini(monkeypatch, tmp_path):
    """DEMO_MODE no longer skips a real key. A placeholder key still does not call."""
    monkeypatch.setattr(settings, "DEMO_MODE", True)
    monkeypatch.setattr(settings, "GEMINI_ENABLED", True)
    monkeypatch.setattr(settings, "AI_MODE", "auto")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key-not-a-secret")
    monkeypatch.setattr("app.llm.client.CACHE_DIR", tmp_path)
    llm_client._memory_cache.clear()
    llm_client._memory_source.clear()
    calls = {"n": 0}

    def fake_call(system, user, timeout_s=12.0):
        calls["n"] += 1
        return _intake_json("medical", "from-gemini-in-demo")

    monkeypatch.setattr(llm_client, "_call_gemini", fake_call)
    extracted = intake_agent.parse_report(f"ZXDEMO{uuid.uuid4().hex[:8]} send a boat")
    assert calls["n"] == 1
    assert extracted.notes == "from-gemini-in-demo"
    assert llm_client.last_ai.provider == "gemini"

    monkeypatch.setattr(settings, "GEMINI_API_KEY", "replace-me")
    llm_client._memory_cache.clear()
    blocked = intake_agent.parse_report(f"ZXNOKEY{uuid.uuid4().hex[:8]} send a boat")
    assert calls["n"] == 1
    assert llm_client.last_ai.provider == "fallback"
    assert llm_client.last_ai.fallback_reason == "no_api_key"
    assert blocked.notes != "from-gemini-in-demo"


def test_chat_intake_uses_the_same_live_client(live_gemini, monkeypatch):
    def fake_call(system, user, timeout_s=12.0):
        return _intake_json("shelter", "chat-gemini")

    monkeypatch.setattr(llm_client, "_call_gemini", fake_call)
    reply = chat_intake_agent.process_turn(
        session_id=f"sess-{uuid.uuid4().hex[:8]}",
        user_message=f"ZXCHAT{uuid.uuid4().hex[:8]} the roof is gone",
        lang_override="en",
    )
    assert reply.bot_message
    assert llm_client.last_source == "gemini"


def test_explainer_uses_gemini_when_live_and_the_template_in_demo(live_gemini, monkeypatch, tmp_path):
    request = StoredRequest(id="req_x", people_count=4, type=IncidentType.RESCUE)
    resource = StoredResource(
        id="res_x",
        kind=ResourceKind.BOAT,
        name="Test Boat",
        ward_id="ward_3",
        lat=9.4,
        lng=76.4,
        capacity_total=8,
        capacity_remaining=6,
    )
    breakdown = MatchBreakdown(
        distance_km=2,
        distance_score=20,
        capacity_fit_score=10,
        urgency_score=10,
        vulnerability_fit_score=10,
        total_score=80,
    )
    calls = {"n": 0}

    def fake_call(system, user, timeout_s=12.0):
        calls["n"] += 1
        return json.dumps(
            {
                "text_en": "Test Boat is 2 km away with 6 seats for 4 people. Total score is 80.",
                "text_hi": "नाव 2 किमी दूर है।",
            }
        )

    monkeypatch.setattr(llm_client, "_call_gemini", fake_call)
    live = explainer_agent.explain(request, resource, breakdown)
    assert calls["n"] == 1
    assert live.text_en.startswith("Test Boat is 2 km")
    assert llm_client.last_source == "gemini"

    monkeypatch.setattr(settings, "GEMINI_API_KEY", "replace-me")
    llm_client._memory_cache.clear()
    llm_client._memory_source.clear()
    for cached in tmp_path.glob("*.json"):
        cached.unlink()
    offline = explainer_agent.explain(request, resource, breakdown)
    assert calls["n"] == 1
    assert "Total match score" in offline.text_en


def test_dedupe_accepts_a_real_candidate_and_ignores_a_bogus_id(live_gemini, monkeypatch):
    candidate = StoredRequest(
        id="req_known",
        type=IncidentType.RESCUE,
        place_text="Nowhere Lane",
        people_count=4,
        lat=9.45,
        lng=76.39,
    )
    new_req = ExtractedRequest(
        type=IncidentType.RESCUE,
        place_text="Nowhere Lane",
        people=PeopleInfo(count=4),
    )

    def good(system, user, timeout_s=12.0):
        return json.dumps(
            {
                "decision": "duplicate",
                "target_request_id": "req_known",
                "changed_fields": {},
                "evidence": ["same street and people"],
                "confidence": 0.9,
            }
        )

    monkeypatch.setattr(llm_client, "_call_gemini", good)
    decision = dedupe_agent.evaluate(f"ZXDED{uuid.uuid4().hex[:8]} same people", new_req, [candidate])
    assert decision.decision.value == "duplicate"
    assert decision.target_request_id == "req_known"

    def bogus(system, user, timeout_s=12.0):
        return json.dumps(
            {
                "decision": "duplicate",
                "target_request_id": "req_not_a_candidate",
                "changed_fields": {},
                "evidence": ["invented id"],
                "confidence": 0.9,
            }
        )

    monkeypatch.setattr(llm_client, "_call_gemini", bogus)
    llm_client._memory_cache.clear()
    fallback = dedupe_agent.evaluate(f"ZXBOG{uuid.uuid4().hex[:8]} other house", new_req, [candidate])
    assert fallback.target_request_id != "req_not_a_candidate"


def test_live_report_stores_gemini_and_demo_stores_offline(live_gemini, monkeypatch):
    def fake_call(system, user, timeout_s=12.0):
        return _intake_json("food", "stored-gemini")

    monkeypatch.setattr(llm_client, "_call_gemini", fake_call)
    token = f"ZXAPI{uuid.uuid4().hex[:8]}"
    created = client.post(
        "/api/reports",
        json={
            "text": f"{token} waiting beside the old tree",
            "lang": "en",
            "channel": "text",
            "location_pin": {"lat": 9.45, "lng": 76.39},
            "idempotency_key": f"gem-{token}",
        },
    )
    assert created.status_code == 200, created.text
    listed = client.get("/api/requests", headers=AUTH)
    match = [row for row in listed.json() if token in (row.get("raw_text") or "")]
    assert match
    assert match[0]["ai_source"] == "gemini"
    assert match[0]["ai"]["provider"] == "gemini"
    assert match[0]["ai"]["model"] == settings.GEMINI_MODEL
    assert match[0]["ai"]["cached"] is False
    assert "latency_ms" in match[0]["ai"]
    assert "tokens" in match[0]["ai"]
    assert match[0]["ai"]["fallback_reason"] is None

    monkeypatch.setattr(settings, "GEMINI_API_KEY", "replace-me")
    calls = {"n": 0}

    def should_not(system, user, timeout_s=12.0):
        calls["n"] += 1
        return _intake_json("medical", "nope")

    monkeypatch.setattr(llm_client, "_call_gemini", should_not)
    llm_client._memory_cache.clear()
    token2 = f"ZXOFF{uuid.uuid4().hex[:8]}"
    created2 = client.post(
        "/api/reports",
        json={
            "text": f"{token2} send a boat please",
            "lang": "en",
            "channel": "text",
            "location_pin": {"lat": 9.46, "lng": 76.4},
            "idempotency_key": f"off-{token2}",
        },
    )
    assert created2.status_code == 200, created2.text
    assert calls["n"] == 0
    listed2 = client.get("/api/requests", headers=AUTH)
    match2 = [row for row in listed2.json() if token2 in (row.get("raw_text") or "")]
    assert match2
    assert match2[0]["ai_source"] == "offline_fallback"
    assert match2[0]["ai"]["provider"] == "fallback"
    assert match2[0]["ai"]["fallback_reason"] == "no_api_key"


def test_quota_and_invalid_json_fall_back(live_gemini, monkeypatch):
    calls = {"n": 0}

    def quota(system, user, timeout_s=12.0):
        calls["n"] += 1
        raise RuntimeError("429 RESOURCE_EXHAUSTED")

    monkeypatch.setattr(llm_client, "_call_gemini", quota)
    intake_agent.parse_report(f"ZX429{uuid.uuid4().hex[:8]} send a boat")
    assert calls["n"] == 1
    assert llm_client.last_ai.provider == "fallback"
    assert llm_client.last_ai.fallback_reason == "quota"

    def bad_json(system, user, timeout_s=12.0):
        calls["n"] += 1
        return "this is not json"

    monkeypatch.setattr(llm_client, "_call_gemini", bad_json)
    intake_agent.parse_report(f"ZXBAD{uuid.uuid4().hex[:8]} five people need a boat")
    assert calls["n"] == 3
    assert llm_client.last_ai.provider == "fallback"
    assert llm_client.last_ai.fallback_reason == "invalid_json"


def test_replay_cache_does_not_call_gemini(live_gemini, monkeypatch):
    calls = {"n": 0}

    def fake_call(system, user, timeout_s=12.0):
        calls["n"] += 1
        return _intake_json("food", "recorded-once")

    monkeypatch.setattr(llm_client, "_call_gemini", fake_call)
    text = f"ZXCACHE{uuid.uuid4().hex[:8]} ration please"
    intake_agent.parse_report(text, language_hint="en")
    assert calls["n"] == 1
    monkeypatch.setattr(settings, "AI_MODE", "replay")
    intake_agent.parse_report(text, language_hint="en")
    assert calls["n"] == 1
    assert llm_client.last_ai.provider == "cache"
    assert llm_client.last_ai.cached is True
    assert llm_client.last_ai.badge() == "recorded"


def test_live_gemini_smoke():
    import os

    key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not key or key in ("replace-me", "synthetic-demo-gemini-key"):
        pytest.skip("Set GEMINI_API_KEY to run the live smoke test")
    from app.llm.client import LLMClient

    live = LLMClient()
    text = live.generate_content(
        system_instruction="Reply with the single word pong.",
        user_prompt="ping",
    )
    assert text.strip()
    assert live.last_ai.provider == "gemini"
