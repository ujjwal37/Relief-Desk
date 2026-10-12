"""A slow or hanging Gemini call must fall back quickly and free its slot."""
import threading
import time
import uuid

from app.config import settings
from app.llm.client import llm_client


class _HangingModels:
    def __init__(self, release: threading.Event):
        self.release = release

    def generate_content(self, **kwargs):
        self.release.wait(30)
        raise RuntimeError("released")


class _HangingClient:
    def __init__(self, release):
        self.models = _HangingModels(release)


def test_hanging_gemini_falls_back_within_15s(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    monkeypatch.setattr(settings, "GEMINI_ENABLED", True)
    monkeypatch.setattr(settings, "AI_MODE", "auto")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key-not-a-secret")
    monkeypatch.setattr(settings, "GEMINI_TIMEOUT_S", 2.0)
    monkeypatch.setattr("app.llm.client.CACHE_DIR", tmp_path)
    monkeypatch.setattr(llm_client.guard, "circuit_open", lambda: False)
    monkeypatch.setattr(llm_client.guard, "sleep", lambda s: None)
    release = threading.Event()
    seen = {}

    def factory(timeout_s):
        seen["timeout_s"] = timeout_s
        return _HangingClient(release)

    monkeypatch.setattr(llm_client, "_make_genai_client", factory)
    slots_before = llm_client.guard.semaphore._value
    started = time.perf_counter()
    try:
        llm_client.generate_content("system", f"ZXHANG{uuid.uuid4().hex[:8]} three people need a boat")
        elapsed = time.perf_counter() - started
    finally:
        release.set()
    assert elapsed < 15
    assert llm_client.last_ai.provider == "fallback"
    assert llm_client.last_ai.fallback_reason == "timeout"
    assert seen["timeout_s"] == 2.0
    assert llm_client.guard.semaphore._value == slots_before
