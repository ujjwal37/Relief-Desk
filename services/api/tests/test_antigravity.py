"""Antigravity local provider: mocked subprocess only. Never runs the real CLI."""
import json
import subprocess

import pytest

from app.config import settings
from app.llm import antigravity as ag
from app.llm import client as llm


class _Proc:
    def __init__(self, stdout, returncode=0, stderr=""):
        self.stdout, self.returncode, self.stderr = stdout, returncode, stderr


def _env(response, status="SUCCESS"):
    return json.dumps({"status": status, "response": response, "usage": {"total_tokens": 42}})


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "antigravity", raising=False)
    monkeypatch.setattr(settings, "AI_MODE", "auto")
    monkeypatch.setattr(settings, "ANTIGRAVITY_BIN", "agy", raising=False)
    llm.llm_client.guard.failures = 0
    yield
    llm.llm_client.guard.failures = 0


def test_off_by_default():
    from app.config import Settings

    assert (Settings.model_fields["LLM_PROVIDER"].default or "") == ""


def test_refused_in_replay_and_tests(on, monkeypatch):
    assert not ag.antigravity_enabled()  # under pytest
    assert ag.antigravity_enabled(allow_in_tests=True)
    monkeypatch.setattr(settings, "AI_MODE", "replay")
    assert not ag.antigravity_enabled(allow_in_tests=True)


def test_call_parses_envelope_and_extracts_json(on):
    seen = {}

    def run(cmd, **kw):
        seen["cmd"], seen["kw"] = cmd, kw
        return _Proc(_env('Sure:\n```json\n{"type": "food"}\n```'))

    text, tokens = ag.call_antigravity("SYS", "USER", timeout_s=30, run=run)
    assert ag.extract_json(text) == '{"type": "food"}' and tokens == 42
    assert "--print" in seen["cmd"] and "--output-format" in seen["cmd"]
    assert "--dangerously-skip-permissions" not in seen["cmd"]
    assert seen["kw"]["timeout"] == 40


def test_call_failures_raise(on):
    with pytest.raises(RuntimeError):
        ag.call_antigravity("S", "U", run=lambda c, **k: _Proc("", returncode=1, stderr="boom"))
    with pytest.raises(RuntimeError):
        ag.call_antigravity("S", "U", run=lambda c, **k: _Proc(_env("x", status="ERROR")))

    def slow(c, **k):
        raise subprocess.TimeoutExpired(c, 1)

    with pytest.raises(TimeoutError):
        ag.call_antigravity("S", "U", run=slow)


def test_client_labels_provider_and_falls_back(on, monkeypatch):
    monkeypatch.setattr(ag, "antigravity_enabled", lambda allow_in_tests=False: True)
    monkeypatch.setattr(ag, "call_antigravity", lambda s, u, timeout_s=None: ('{"a": 1}', 7))
    out = llm.llm_client.generate_content(system_instruction="S-ag-1", user_prompt="U-ag-1",
                                          validator=lambda t: json.loads(t))
    assert json.loads(out) == {"a": 1}
    assert llm.llm_client.last_ai.provider == "antigravity-local"
    assert llm.llm_client.last_ai.badge() == "local"

    def boom(s, u, timeout_s=None):
        raise RuntimeError("cli down")

    monkeypatch.setattr(ag, "call_antigravity", boom)
    llm.llm_client.generate_content(system_instruction="S-ag-2", user_prompt="U-ag-2")
    assert llm.llm_client.last_ai.provider == "fallback"


def test_benchmark_and_record_refuse_antigravity(on):
    with pytest.raises(RuntimeError):
        ag.assert_not_antigravity("bench")
    from app.llm.record import record_seeded_reports

    with pytest.raises(RuntimeError):
        record_seeded_reports()


def test_ask_desk_via_antigravity(on, monkeypatch):
    from app.agents import desk_query as dq

    monkeypatch.setattr(ag, "antigravity_enabled", lambda allow_in_tests=False: True)
    monkeypatch.setattr(ag, "call_antigravity",
                        lambda s, u, timeout_s=None: ('{"ward_ids": ["ward_4"], "vulnerable": ["elderly"], "reason": "r"}', 5))
    f, meta = dq.gemini_filters("elderly in Aluva")
    assert meta["provider"] == "antigravity-local" and f["ward_ids"] == ["ward_4"]
