"""AI_MODE=replay serves data/ai_cache. A missing key does not invent a recording."""
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agents.intake import SYSTEM_INTAKE_PROMPT, intake_user_prompt
from app.config import settings
from app.llm.client import llm_client
from app.llm.record import require_real_key
from app.main import app
from tests.test_gemini_live import _intake_json

client = TestClient(app)
AUTH = {"Authorization": "Bearer demo-coordinator-token"}
ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def live_gemini(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    monkeypatch.setattr(settings, "GEMINI_ENABLED", True)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key-not-a-secret")
    monkeypatch.setattr(settings, "AI_MODE", "auto")
    monkeypatch.setattr("app.llm.client.CACHE_DIR", tmp_path / "runtime")
    (tmp_path / "runtime").mkdir()
    llm_client._memory_cache.clear()
    llm_client._memory_source.clear()
    llm_client._memory_meta.clear()
    llm_client.call_count = 0
    yield
    llm_client._memory_cache.clear()
    llm_client._memory_source.clear()
    llm_client._memory_meta.clear()


def test_record_ai_refuses_placeholder_keys():
    for key in ("", "replace-me", "synthetic-demo-gemini-key", "  replace-me  "):
        with pytest.raises(SystemExit, match="No file was written"):
            require_real_key(key)
    assert require_real_key("not-a-placeholder") == "not-a-placeholder"


def test_record_ai_script_writes_nothing_without_a_key():
    env = os.environ.copy()
    env["GEMINI_API_KEY"] = "replace-me"
    env["AI_MODE"] = "auto"
    before = {path.name for path in (ROOT / "data" / "ai_cache").glob("*")}
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "record_ai.py")],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    after = {path.name for path in (ROOT / "data" / "ai_cache").glob("*")}
    assert result.returncode != 0
    assert "No file was written" in (result.stderr + result.stdout)
    assert after == before


def test_replay_serves_recorded_file_and_new_text_stays_live(live_gemini, monkeypatch, tmp_path):
    replay = tmp_path / "replay"
    replay.mkdir()
    monkeypatch.setattr("app.llm.client.REPLAY_DIR", replay)
    monkeypatch.setattr(settings, "AI_MODE", "replay")
    llm_client._memory_cache.clear()
    llm_client._memory_source.clear()
    llm_client._memory_meta.clear()

    recorded_text = f"ZXREC{uuid.uuid4().hex[:8]} ration near the school"
    user_prompt = intake_user_prompt(recorded_text, "en")
    digest = llm_client.cache_key(SYSTEM_INTAKE_PROMPT, user_prompt)
    (replay / f"{digest}.json").write_text(
        json.dumps(
            {
                "key": digest,
                "response": _intake_json("food", "recorded-file"),
                "source": "gemini",
                "provider": "gemini",
                "model": "gemini-3.8-flash",
                "tokens": 42,
                "report_id": "DR-TEST",
            }
        ),
        encoding="utf-8",
    )

    calls = {"intake": 0}

    def fake_call(system, user, timeout_s=12.0):
        if "crisis report parser" in system:
            calls["intake"] += 1
            return _intake_json("rescue", "live-new")
        return json.dumps(
            {
                "relation": "distinct",
                "target_request_id": None,
                "evidence": ["different place"],
                "confidence": 0.4,
            }
        )

    monkeypatch.setattr(llm_client, "_call_gemini", fake_call)
    created = client.post(
        "/api/reports",
        json={
            "text": recorded_text,
            "lang": "en",
            "channel": "text",
            "location_pin": {"lat": 8.2, "lng": 76.1},
            "idempotency_key": f"rec-{digest[:8]}",
        },
    )
    assert created.status_code == 200, created.text
    assert calls["intake"] == 0
    listed = client.get("/api/requests", headers=AUTH)
    match = [row for row in listed.json() if recorded_text in (row.get("raw_text") or "")]
    assert match
    assert match[0]["ai_source"] == "recorded"
    assert match[0]["ai"]["provider"] == "cache"
    assert match[0]["ai"]["cached"] is True
    assert match[0]["ai"]["model"] == "gemini-3.8-flash"

    fresh = f"ZXNEW{uuid.uuid4().hex[:8]} people waiting by a unique marker"
    llm_client._memory_cache.clear()
    llm_client._memory_source.clear()
    llm_client._memory_meta.clear()
    created_new = client.post(
        "/api/reports",
        json={
            "text": fresh,
            "lang": "en",
            "channel": "text",
            "location_pin": {"lat": 8.21, "lng": 76.11},
            "idempotency_key": f"new-{fresh[-6:]}",
        },
    )
    assert created_new.status_code == 200, created_new.text
    assert calls["intake"] == 1
    listed_new = client.get("/api/requests", headers=AUTH)
    match_new = [row for row in listed_new.json() if fresh in (row.get("raw_text") or "")]
    assert match_new
    assert match_new[0]["ai_source"] == "gemini"
    assert match_new[0]["ai"]["provider"] == "gemini"
    assert match_new[0]["ai"]["cached"] is False
