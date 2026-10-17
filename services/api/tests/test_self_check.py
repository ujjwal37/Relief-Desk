"""Self-check with a mocked Gemini: accepted only with a real quote."""
from types import SimpleNamespace

import pytest

from app.agents import self_check as sc


def _req(text, people=1, place="Chalakudy"):
    return SimpleNamespace(raw_text=text, people_count=people, place_text=place, channel="text",
                           type=SimpleNamespace(value="rescue"))


class FakeClient:
    def __init__(self, raw, provider="gemini"):
        self.raw = raw
        self._memory_source = {}
        self.last_ai = SimpleNamespace(provider=provider, model="gemini-test", latency_ms=12,
                                       model_copy=lambda: self.last_ai)

    def cache_key(self, a, b):
        return "k"

    def get_cached(self, key):
        return None

    def gemini_live(self):
        return True

    def generate_content(self, system, prompt, validator=None, max_retries=0):
        if validator:
            validator(self.raw)
        return self.raw


@pytest.fixture
def patch_client(monkeypatch):
    def use(raw, provider="gemini"):
        fake = FakeClient(raw, provider)
        monkeypatch.setattr(sc, "llm_client", fake)
        return fake
    return use


ML = "ആലുവയിൽ ഒരു വീടിന്റെ ടെറസിൽ 6 പേർ കുടുങ്ങിയിരിക്കുന്നു"


def test_fix_with_real_quote_is_applied(patch_client):
    patch_client('{"verdict":"fix","people_count":6,"place_text":"Aluva","evidence":"ടെറസിൽ 6 പേർ","reason":"Report says 6 people in Aluva."}')
    req = _req(ML)
    out = sc.self_check(req)
    assert out["verdict"] == "fixed"
    assert req.people_count == 6 and req.place_text == "Aluva"
    assert out["provider"] == "gemini"


def test_fix_with_invented_quote_is_dropped(patch_client):
    patch_client('{"verdict":"fix","people_count":9,"place_text":null,"evidence":"9 people trapped","reason":"x"}')
    req = _req(ML)
    out = sc.self_check(req)
    assert out["verdict"] == "pass" and req.people_count == 1


def test_number_not_in_quote_is_dropped(patch_client):
    patch_client('{"verdict":"fix","people_count":7,"place_text":null,"evidence":"ടെറസിൽ 6 പേർ","reason":"x"}')
    req = _req(ML)
    sc.self_check(req)
    assert req.people_count == 1


def test_recorded_replay_is_labelled(patch_client):
    patch_client('{"verdict":"pass","evidence":"","reason":"Matches."}', provider="cache")
    out = sc.self_check(_req(ML))
    assert out["provider"] == "cache" and out["verdict"] == "pass"


def test_no_gemini_no_recording_is_not_run(monkeypatch, patch_client):
    fake = patch_client('{}')
    monkeypatch.setattr(fake, "gemini_live", lambda: False)
    out = sc.self_check(_req(ML))
    assert out["verdict"] == "not_run" and out["provider"] == "tool"


def test_plain_english_multi_person_skips_call():
    assert sc.should_check(_req("5 people on a roof in Aluva", people=5, place="Aluva")) is False
