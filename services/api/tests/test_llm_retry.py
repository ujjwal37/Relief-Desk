"""One short retry on a transient Gemini error, never on quota."""
import uuid

import pytest

from app.config import settings
from app.llm.client import llm_client


class _Err(Exception):
    def __init__(self, code, msg):
        super().__init__(f"{code} {msg}")
        self.code = code


@pytest.fixture
def live(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "GEMINI_ENABLED", True)
    monkeypatch.setattr(settings, "AI_MODE", "auto")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key-not-a-secret")
    monkeypatch.setattr("app.llm.client.CACHE_DIR", tmp_path)
    monkeypatch.setattr(llm_client.guard, "circuit_open", lambda: False)
    monkeypatch.setattr(llm_client.guard, "failures", 0)
    monkeypatch.setattr(llm_client.guard, "sleep", lambda s: None)


@pytest.mark.parametrize("code", [503, 504])
def test_transient_error_is_retried_once(live, monkeypatch, code):
    calls = {"n": 0}

    def flaky(system, user, timeout_s=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _Err(code, "UNAVAILABLE")
        return "ok"

    monkeypatch.setattr(llm_client, "_call_gemini", flaky)
    assert llm_client.generate_content("s", f"ZXRETRY{uuid.uuid4().hex}") == "ok"
    assert calls["n"] == 2
    assert llm_client.last_ai.provider == "gemini"


def test_quota_is_not_retried(live, monkeypatch):
    calls = {"n": 0}

    def quota(system, user, timeout_s=None):
        calls["n"] += 1
        raise _Err(429, "RESOURCE_EXHAUSTED")

    monkeypatch.setattr(llm_client, "_call_gemini", quota)
    llm_client.generate_content("s", f"ZXQUOTA{uuid.uuid4().hex}")
    assert calls["n"] == 1
    assert llm_client.last_ai.fallback_reason == "quota"


def test_second_transient_error_falls_back(live, monkeypatch):
    calls = {"n": 0}

    def down(system, user, timeout_s=None):
        calls["n"] += 1
        raise _Err(503, "UNAVAILABLE")

    monkeypatch.setattr(llm_client, "_call_gemini", down)
    llm_client.generate_content("s", f"ZXDOWN{uuid.uuid4().hex}")
    assert calls["n"] == 2
    assert llm_client.last_ai.provider == "fallback"
