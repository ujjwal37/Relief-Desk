"""Tests for Vertex AI backend with automatic AI Studio fallback.

Requirements:
1. Default (no VERTEX_PROJECT): keeps current behaviour (deterministic fallback when no key, studio client when key is present).
2. With VERTEX_PROJECT set: client is built with vertexai=True, project=VERTEX_PROJECT, location=VERTEX_LOCATION,
   no api_key argument (ADC).
3. Failing vertex client build falls back to studio key path (GEMINI_API_KEY) and logs one warning.
4. Failing vertex call at runtime (401/403/404/auth/permission) falls back to studio key path and logs one warning.
5. Model resolution returns VERTEX_MODEL for vertex and GEMINI_MODEL otherwise.
6. Existing tests must not need any AI env vars.
"""
from unittest.mock import MagicMock, patch
import pytest

from app.config import settings
from app.models.schemas import AiCall
from app.llm.providers import display_name
from app.llm.client import (
    build_genai_client,
    resolve_model,
    reset_vertex_warning,
    _is_vertex_fallback_error,
    llm_client,
)


@pytest.fixture(autouse=True)
def _reset_warnings():
    reset_vertex_warning()
    yield
    reset_vertex_warning()


class DummyResponse:
    def __init__(self, text="Dummy model reply"):
        self.text = text
        self.usage_metadata = MagicMock(total_token_count=42)


def test_default_backend_without_vertex_project(monkeypatch):
    """Default (no VERTEX_PROJECT): keeps current behaviour without requiring any AI env vars."""
    monkeypatch.setattr(settings, "GEMINI_BACKEND", "auto")
    monkeypatch.setattr(settings, "VERTEX_PROJECT", "")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "replace-me")

    assert not settings.is_vertex_backend
    assert not llm_client.vertex_configured()
    assert not llm_client.gemini_live()

    # When key is placeholder and no vertex project, llm_client falls back to deterministic rules
    reply = llm_client.generate_content("system", "3 people need rescue in Aluva")
    assert llm_client.last_ai.provider in ("fallback", "cache")


def test_build_client_default_uses_studio(monkeypatch):
    """When VERTEX_PROJECT is empty, build_genai_client constructs Studio client with api_key."""
    monkeypatch.setattr(settings, "GEMINI_BACKEND", "auto")
    monkeypatch.setattr(settings, "VERTEX_PROJECT", "")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-studio-key")

    mock_client_inst = MagicMock()
    with patch("google.genai.Client", return_value=mock_client_inst) as mock_cls:
        client, provider = build_genai_client(timeout_s=15.0)
        assert provider == "gemini"
        assert client is mock_client_inst

        # Verify Client was called with api_key and NOT with vertexai=True
        mock_cls.assert_called_once()
        kwargs = mock_cls.call_args.kwargs
        assert kwargs.get("api_key") == "test-studio-key"
        assert "vertexai" not in kwargs or kwargs["vertexai"] is not True


def test_build_client_with_vertex_project_uses_adc(monkeypatch):
    """With VERTEX_PROJECT set: client is built with vertexai=True, default location='global', and NO api key."""
    monkeypatch.setattr(settings, "GEMINI_BACKEND", "auto")
    monkeypatch.setattr(settings, "VERTEX_PROJECT", "relief-desk-gcp")
    monkeypatch.setattr(settings, "VERTEX_LOCATION", "global")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "studio-key-should-not-be-used")

    assert settings.is_vertex_backend
    assert llm_client.vertex_configured()
    assert llm_client.gemini_live()

    mock_client_inst = MagicMock()
    with patch("google.genai.Client", return_value=mock_client_inst) as mock_cls:
        client, provider = build_genai_client(timeout_s=15.0)
        assert provider == "vertex"
        assert client is mock_client_inst

        mock_cls.assert_called_once()
        kwargs = mock_cls.call_args.kwargs
        assert kwargs.get("vertexai") is True
        assert kwargs.get("project") == "relief-desk-gcp"
        assert kwargs.get("location") == "global"
        # Crucial requirement: No API key passed for Vertex AI ADC client
        assert "api_key" not in kwargs or kwargs["api_key"] is None


def test_default_vertex_location_is_global():
    """Default Vertex location must be global (asia-south1 returns 417 for gemini-2.5-flash)."""
    from app.config import Settings
    fresh_settings = Settings()
    assert fresh_settings.VERTEX_LOCATION == "global"


def test_explicit_vertex_backend_setting(monkeypatch):
    """GEMINI_BACKEND='vertex' builds vertex client; GEMINI_BACKEND='studio' forces studio."""
    monkeypatch.setattr(settings, "GEMINI_BACKEND", "vertex")
    monkeypatch.setattr(settings, "VERTEX_PROJECT", "relief-desk")
    assert settings.is_vertex_backend

    mock_client_inst = MagicMock()
    with patch("google.genai.Client", return_value=mock_client_inst) as mock_cls:
        _, provider = build_genai_client()
        assert provider == "vertex"
        assert mock_cls.call_args.kwargs.get("vertexai") is True

    # Forced studio backend even if VERTEX_PROJECT is present
    monkeypatch.setattr(settings, "GEMINI_BACKEND", "studio")
    assert not settings.is_vertex_backend
    with patch("google.genai.Client", return_value=mock_client_inst) as mock_cls:
        _, provider = build_genai_client()
        assert provider == "gemini"
        assert "vertexai" not in mock_cls.call_args.kwargs


def test_vertex_client_build_failure_falls_back_to_studio(monkeypatch, caplog):
    """If the Vertex client fails to build (e.g. ADC credentials missing), fall back to AI Studio."""
    monkeypatch.setattr(settings, "GEMINI_BACKEND", "auto")
    monkeypatch.setattr(settings, "VERTEX_PROJECT", "relief-desk")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "fallback-studio-key")

    studio_client = MagicMock()

    def client_factory(*args, **kwargs):
        if kwargs.get("vertexai"):
            raise RuntimeError("DefaultCredentialsError: Could not automatically determine credentials")
        return studio_client

    with patch("google.genai.Client", side_effect=client_factory):
        import logging
        with caplog.at_level(logging.WARNING):
            client, provider = build_genai_client(timeout_s=10.0)

        assert provider == "gemini"
        assert client is studio_client
        assert "falling back to AI Studio" in caplog.text
        # Ensure credentials / keys are NEVER logged
        assert "fallback-studio-key" not in caplog.text


def test_vertex_runtime_error_fallback(monkeypatch, caplog):
    """If a Vertex call fails with auth/permission/403/404, fall back to Studio key path."""
    monkeypatch.setattr(settings, "GEMINI_BACKEND", "auto")
    monkeypatch.setattr(settings, "VERTEX_PROJECT", "relief-desk")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "real-studio-key-123")

    vertex_client = MagicMock()
    # 403 Permission Denied on vertex call
    perm_err = Exception("403 PermissionDenied: The caller does not have permission")
    vertex_client.models.generate_content.side_effect = perm_err

    studio_client = MagicMock()
    studio_client.models.generate_content.return_value = DummyResponse("Fallback response from studio")

    def client_factory(*args, **kwargs):
        if kwargs.get("vertexai"):
            return vertex_client
        return studio_client

    with patch("google.genai.Client", side_effect=client_factory):
        import logging
        with caplog.at_level(logging.WARNING):
            reply = llm_client._call_with_retry(
                system_instruction="You are an assistant.",
                user_prompt="Need assistance urgently.",
            )

        assert reply == "Fallback response from studio"
        assert llm_client.last_ai.provider == "gemini"
        assert "falling back to AI Studio" in caplog.text
        assert "real-studio-key-123" not in caplog.text


def test_vertex_fallback_error_detection():
    """Verify _is_vertex_fallback_error correctly identifies auth, permission, 401, 403, 404, 417."""
    class MockError(Exception):
        def __init__(self, msg, code=None):
            super().__init__(msg)
            self.code = code

    assert _is_vertex_fallback_error(MockError("unauthenticated", code=401))
    assert _is_vertex_fallback_error(MockError("permission denied", code=403))
    assert _is_vertex_fallback_error(MockError("model not found", code=404))
    assert _is_vertex_fallback_error(MockError("expectation failed", code=417))
    assert _is_vertex_fallback_error(Exception("417 Expectation Failed: model not available in region"))
    assert _is_vertex_fallback_error(Exception("DefaultCredentialsError: no credentials"))
    assert _is_vertex_fallback_error(Exception("403 Forbidden: IAM role missing"))
    # Transient errors like 500/503 are not vertex credential fallback triggers
    assert not _is_vertex_fallback_error(MockError("503 Service Unavailable", code=503))


def test_model_resolution(monkeypatch):
    """resolve_model returns VERTEX_MODEL for vertex and GEMINI_MODEL otherwise."""
    monkeypatch.setattr(settings, "GEMINI_MODEL", "gemini-2.5-flash")
    monkeypatch.setattr(settings, "VERTEX_MODEL", "gemini-2.5-flash-vertex")

    assert resolve_model(provider="gemini") == "gemini-2.5-flash"
    assert resolve_model(provider="vertex") == "gemini-2.5-flash-vertex"


def test_ai_call_badge_and_provider_display():
    """AiCall badge and display_name show Vertex AI for vertex provider."""
    vertex_call = AiCall(provider="vertex", model="gemini-2.5-flash", latency_ms=120)
    assert vertex_call.badge() == "vertex"
    assert display_name("vertex") == "Vertex AI"

    gemini_call = AiCall(provider="gemini", model="gemini-2.5-flash", latency_ms=150)
    assert gemini_call.badge() == "gemini"
    assert display_name("gemini") == "Gemini"

    fallback_call = AiCall(provider="fallback")
    assert fallback_call.badge() == "offline"
    assert display_name("fallback") == "Rules"
