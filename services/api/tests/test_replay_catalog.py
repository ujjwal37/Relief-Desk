"""The replay fixture lists prompts and stores no invented Gemini replies."""
import json
from pathlib import Path

from app.agents.intake import SYSTEM_INTAKE_PROMPT, intake_user_prompt
from app.config import settings
from app.llm.client import llm_client
from app.llm.replay_catalog import SCRIPTED_PHONE_REPORTS, catalog_keys, catalog_rows

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "data" / "ai_cache" / "fixture.json"


def test_catalog_covers_the_demo_seed_and_scripted_phone_lines():
    rows = {row["id"]: row for row in catalog_rows()}
    assert "DR-001" in rows
    assert "INC-001" in rows
    assert "नाव" in (rows["INC-001"]["text"] or "")
    for report in SCRIPTED_PHONE_REPORTS:
        assert rows[report["id"]]["text"] == report["text"]
    assert len(catalog_keys()) == len(catalog_rows())


def test_committed_fixture_has_no_model_replies():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert payload["status"] == "pending"
    items = payload["items"]
    assert items
    assert {row["id"] for row in items} == {row["id"] for row in catalog_rows()}
    assert all(row.get("response") is None for row in items)


def test_replay_does_not_call_gemini_for_a_pending_catalog_prompt(monkeypatch):
    monkeypatch.setattr(settings, "AI_MODE", "replay")
    monkeypatch.setattr(settings, "GEMINI_ENABLED", True)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key-not-a-secret")
    calls = {"n": 0}

    def boom(system, user, timeout_s=12.0):
        calls["n"] += 1
        raise AssertionError("live Gemini call")

    monkeypatch.setattr(llm_client, "_call_gemini", boom)
    llm_client._memory_cache.clear()
    llm_client._memory_source.clear()
    llm_client._memory_meta.clear()
    report = SCRIPTED_PHONE_REPORTS[1]
    text = llm_client.generate_content(
        system_instruction=SYSTEM_INTAKE_PROMPT,
        user_prompt=intake_user_prompt(report["text"], report["lang"]),
    )
    assert calls["n"] == 0
    assert text
    assert llm_client.last_ai.provider == "fallback"
    assert llm_client.last_ai.fallback_reason == "replay_pending"
