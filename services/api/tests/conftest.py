"""Tests never spend Gemini quota, whatever is in the developer's services/api/.env.

The environment is set before the app is imported (settings read it at import),
and an autouse fixture puts the placeholder key back for every test, so gemini_live() is False. Tests that need
"live" Gemini set a fake key themselves and mock the client.
"""
import os

os.environ["GEMINI_API_KEY"] = "replace-me"
os.environ["VERTEX_PROJECT"] = ""
os.environ["GEMINI_BACKEND"] = "auto"
# Tests sign coordinator JWTs. Production has no source default; this value is test-only.
os.environ["JWT_SECRET"] = "test-only-jwt-secret-not-for-production"

import pytest  # noqa: E402

from app.config import settings  # noqa: E402


@pytest.fixture(autouse=True)
def _no_live_gemini(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "replace-me")
    monkeypatch.setattr(settings, "VERTEX_PROJECT", "")
    monkeypatch.setattr(settings, "GEMINI_BACKEND", "auto")
    from app.llm.client import llm_client
    llm_client.guard.failures = 0
    llm_client.guard.opened_at = 0.0
    yield
    llm_client.guard.failures = 0
    llm_client.guard.opened_at = 0.0


@pytest.fixture(autouse=True)
def _finish_intake_inside_the_request(monkeypatch):
    """Tests read the finished case from the POST body.

    Production starts a thread and returns first. A test that checks that
    path replaces `_spawn` itself.
    """
    monkeypatch.setattr("app.agents.pipeline._spawn", lambda fn: fn())