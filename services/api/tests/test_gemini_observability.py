import logging
import re
import uuid
import pytest
from app.config import settings
from app.llm.client import llm_client
from app.models.firestore_models import StoredRequest
from app.models.schemas import AiCall
from app.agents.pipeline import _intake_row


class MockResponse:
    def __init__(self, text='{"type": "rescue", "notes": "ok"}', tokens=42):
        self.text = text
        self.usage_metadata = type("Usage", (), {"total_token_count": tokens})()


class MockModels:
    def __init__(self, generate_fn=None):
        self._generate_fn = generate_fn or (lambda **kw: MockResponse())

    def generate_content(self, **kwargs):
        return self._generate_fn(**kwargs)


class MockClient:
    def __init__(self, models=None):
        self.models = models or MockModels()

    def close(self):
        pass


def test_gemini_observability_vertex_call(monkeypatch, caplog):
    # Mock settings without any network or real AI env vars
    monkeypatch.setattr(settings, "GEMINI_BACKEND", "vertex")
    monkeypatch.setattr(settings, "VERTEX_PROJECT", "mock-vertex-project")
    monkeypatch.setattr(settings, "VERTEX_LOCATION", "us-central1")
    monkeypatch.setattr(settings, "VERTEX_MODEL", "gemini-2.5-flash")
    monkeypatch.setattr(settings, "AI_MODE", "live")
    monkeypatch.setattr(settings, "GEMINI_ENABLED", True)
    monkeypatch.setattr(llm_client, "vertex_configured", lambda: True)
    monkeypatch.setattr(llm_client, "gemini_live", lambda: True)

    vertex_called = False

    def mock_generate(**kwargs):
        nonlocal vertex_called
        vertex_called = True
        return MockResponse('{"result": "vertex_success"}')

    def mock_client_init(*args, **kwargs):
        assert kwargs.get("vertexai") is True
        assert kwargs.get("project") == "mock-vertex-project"
        return MockClient(MockModels(mock_generate))

    monkeypatch.setattr("google.genai.Client", mock_client_init)

    unique_prompt = f"Rescue test prompt {uuid.uuid4()}"
    with caplog.at_level(logging.INFO, logger="relief_desk.llm"):
        res = llm_client.generate_content(
            system_instruction="You are a test assistant.",
            user_prompt=unique_prompt,
        )

    assert vertex_called is True
    assert res == '{"result": "vertex_success"}'

    # Assert trace provider and model on last_ai
    assert llm_client.last_ai.provider == "vertex"
    assert llm_client.last_ai.model == "gemini-2.5-flash"

    # Assert case AI trace on StoredRequest
    req = StoredRequest(
        id="req_vertex_test",
        raw_text=unique_prompt,
        summary="Rescue test",
        ai_source="vertex",
        ai=llm_client.last_ai.model_copy(),
    )
    trace_row = _intake_row(req, "Rescue test", 0.0)
    assert trace_row["provider"] == "vertex"
    assert trace_row["model"] == "gemini-2.5-flash"

    # Assert exactly one INFO log line in the exact required form:
    # gemini_call provider=vertex|aistudio model=<name> latency_ms=<int> ok=<true|false> fallback_reason=<short reason or none>
    log_lines = [r.message for r in caplog.records if r.message.startswith("gemini_call")]
    assert len(log_lines) == 1
    log = log_lines[0]
    pattern = r"^gemini_call provider=vertex model=gemini-2\.5-flash latency_ms=\d+ ok=true fallback_reason=none$"
    assert re.match(pattern, log), f"Log line did not match expected pattern: {log}"

    # Never log keys, tokens or prompt text
    assert "mock-vertex-project" not in log
    assert unique_prompt not in log
    assert "token" not in log
    assert "tokens" not in log


def test_gemini_observability_aistudio_fallback(monkeypatch, caplog):
    # Vertex is configured, but fails with permission_denied, falling back to AI Studio
    monkeypatch.setattr(settings, "GEMINI_BACKEND", "vertex")
    monkeypatch.setattr(settings, "VERTEX_PROJECT", "mock-vertex-project")
    monkeypatch.setattr(settings, "VERTEX_MODEL", "gemini-2.5-flash")
    monkeypatch.setattr(settings, "GEMINI_MODEL", "gemini-3.8-flash")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "mock-studio-api-key")
    monkeypatch.setattr(settings, "AI_MODE", "live")
    monkeypatch.setattr(settings, "GEMINI_ENABLED", True)
    monkeypatch.setattr(llm_client, "vertex_configured", lambda: True)
    monkeypatch.setattr(llm_client, "studio_key_live", lambda: True)
    monkeypatch.setattr(llm_client, "gemini_live", lambda: True)

    calls = []

    def mock_client_init(*args, **kwargs):
        if kwargs.get("vertexai") is True:
            def vertex_generate(**kw):
                calls.append("vertex")
                exc = Exception("403 Forbidden: Permission denied on vertex project")
                setattr(exc, "status_code", 403)
                raise exc
            return MockClient(MockModels(vertex_generate))
        else:
            def studio_generate(**kw):
                calls.append("studio")
                return MockResponse('{"result": "studio_fallback_success"}')
            return MockClient(MockModels(studio_generate))

    monkeypatch.setattr("google.genai.Client", mock_client_init)

    unique_prompt = f"Studio fallback test prompt {uuid.uuid4()}"
    with caplog.at_level(logging.INFO, logger="relief_desk.llm"):
        res = llm_client.generate_content(
            system_instruction="You are a test assistant.",
            user_prompt=unique_prompt,
        )

    assert calls == ["vertex", "studio"]
    assert res == '{"result": "studio_fallback_success"}'

    # Assert trace provider and model on last_ai
    assert llm_client.last_ai.provider == "gemini"
    assert llm_client.last_ai.model == "gemini-3.8-flash"

    # Assert case AI trace on StoredRequest
    req = StoredRequest(
        id="req_studio_test",
        raw_text=unique_prompt,
        summary="Studio test",
        ai_source="gemini",
        ai=llm_client.last_ai.model_copy(),
    )
    trace_row = _intake_row(req, "Studio test", 0.0)
    assert trace_row["provider"] == "gemini"
    assert trace_row["model"] == "gemini-3.8-flash"

    # Assert exactly one INFO log line in the exact required form:
    # gemini_call provider=vertex|aistudio model=<name> latency_ms=<int> ok=<true|false> fallback_reason=<short reason or none>
    log_lines = [r.message for r in caplog.records if r.message.startswith("gemini_call")]
    assert len(log_lines) == 1
    log = log_lines[0]
    pattern = r"^gemini_call provider=aistudio model=gemini-3\.8-flash latency_ms=\d+ ok=true fallback_reason=permission_denied$"
    assert re.match(pattern, log), f"Log line did not match expected pattern: {log}"

    # Never log keys, tokens or prompt text
    assert "mock-studio-api-key" not in log
    assert unique_prompt not in log
    assert "token" not in log
    assert "tokens" not in log


def test_gemini_observability_build_fallback(monkeypatch, caplog):
    # Vertex client fails at build time, falling back to AI Studio
    monkeypatch.setattr(settings, "GEMINI_BACKEND", "vertex")
    monkeypatch.setattr(settings, "VERTEX_PROJECT", "mock-vertex-project")
    monkeypatch.setattr(settings, "VERTEX_MODEL", "gemini-2.5-flash")
    monkeypatch.setattr(settings, "GEMINI_MODEL", "gemini-3.8-flash")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "mock-studio-api-key")
    monkeypatch.setattr(settings, "AI_MODE", "live")
    monkeypatch.setattr(settings, "GEMINI_ENABLED", True)
    monkeypatch.setattr(llm_client, "vertex_configured", lambda: True)
    monkeypatch.setattr(llm_client, "studio_key_live", lambda: True)
    monkeypatch.setattr(llm_client, "gemini_live", lambda: True)

    def mock_client_init(*args, **kwargs):
        if kwargs.get("vertexai") is True:
            raise Exception("could not automatically determine credentials")
        return MockClient(MockModels(lambda **kw: MockResponse('{"result": "build_fallback_success"}')))

    monkeypatch.setattr("google.genai.Client", mock_client_init)

    unique_prompt = f"Build fallback test prompt {uuid.uuid4()}"
    with caplog.at_level(logging.INFO, logger="relief_desk.llm"):
        res = llm_client.generate_content(
            system_instruction="You are a test assistant.",
            user_prompt=unique_prompt,
        )

    assert res == '{"result": "build_fallback_success"}'
    assert llm_client.last_ai.provider == "gemini"
    assert llm_client.last_ai.model == "gemini-3.8-flash"

    log_lines = [r.message for r in caplog.records if r.message.startswith("gemini_call")]
    assert len(log_lines) == 1
    log = log_lines[0]
    pattern = r"^gemini_call provider=aistudio model=gemini-3\.8-flash latency_ms=\d+ ok=true fallback_reason=auth_error$"
    assert re.match(pattern, log), f"Log line did not match expected pattern: {log}"

    assert "mock-studio-api-key" not in log
    assert unique_prompt not in log
