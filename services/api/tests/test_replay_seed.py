"""Seeded cases pick up a recorded Gemini reading when one exists."""
import json

from app.agents.intake import SYSTEM_INTAKE_PROMPT
from app.llm import client as llm
from app.llm.replay_seed import attach_recorded_ai, seed_prompt
from app.models.firestore_models import StoredRequest


class _Store:
    def __init__(self, rows):
        self._requests = {r.id: r for r in rows}


def test_recorded_seed_shows_cache_provider(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "REPLAY_DIR", tmp_path)
    recorded = StoredRequest(id="INC-T1", raw_text="boat needed at the jetty", synthetic=True)
    plain = StoredRequest(id="INC-T2", raw_text="no recording for this one", synthetic=True)
    key = llm.llm_client.cache_key(SYSTEM_INTAKE_PROMPT, seed_prompt(recorded.raw_text))
    (tmp_path / f"{key}.json").write_text(
        json.dumps({"key": key, "provider": "gemini", "model": "gemini-3.5-flash-lite", "tokens": 700}),
        encoding="utf-8",
    )
    assert attach_recorded_ai(_Store([recorded, plain])) == 1
    assert recorded.ai.provider == "cache"
    assert recorded.ai.model == "gemini-3.5-flash-lite"
    assert recorded.ai_source == "recorded"
    assert plain.ai is None
