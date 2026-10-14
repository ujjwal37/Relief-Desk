"""openai_compat test provider (NVIDIA NIM by default). Every HTTP call is a fake; no network, no real key."""
import copy
import json
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agents import desk_query
from app.agents.intake import IntakeAgent
from app.agents.pipeline import _start_thread, _trace_step, wait_for_idle
from app.config import Settings, settings
from app.llm import embeddings, openai_compat as oc
from app.llm.client import llm_client
from app.llm.providers import assert_gemini_only, display_name
from app.main import app
from app.models.schemas import AiCall
from app.tools.storage import storage_service

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

FAKE_KEY = "nvapi-test-not-a-real-key"


class _Resp:
    def __init__(self, status: int, body):
        self.status_code = status
        self._body = body
        self.text = body if isinstance(body, str) else json.dumps(body)

    def json(self):
        return self._body


class FakeAPI:
    """Answers /chat/completions and /embeddings like NIM, and records every request."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, url, json, headers, timeout):
        self.calls.append({"url": url, "json": copy.deepcopy(json), "headers": headers, "timeout": timeout})
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        return reply(json) if callable(reply) else reply


def chat(content=None, tool_args=None, tokens=50):
    msg = {"role": "assistant", "content": content}
    if tool_args is not None:
        msg["tool_calls"] = [{"type": "function", "function": {"name": "search_cases", "arguments": json.dumps(tool_args)}}]
    return _Resp(200, {"choices": [{"message": msg}], "usage": {"total_tokens": tokens}})


INTAKE = {
    "type": "rescue",
    "place_text": "Gandhi School, Ward 4",
    "people": {"count": 5, "confidence": 0.9},
    "hazard": "water_rising",
    "urgency_hint": "high",
    "language": "en",
    "text_en": "Five people stuck near Gandhi School, water rising.",
    "text_hi": "गांधी स्कूल के पास पाँच लोग फंसे हैं, पानी बढ़ रहा है।",
    "translation_confidence": 0.92,
}


@pytest.fixture
def nim(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai_compat")
    monkeypatch.setattr(settings, "AI_MODE", "auto")
    monkeypatch.setattr(settings, "OPENAI_COMPAT_API_KEY", FAKE_KEY)
    monkeypatch.setattr(settings, "OPENAI_COMPAT_BASE_URL", "https://integrate.api.nvidia.com/v1")
    monkeypatch.setattr(settings, "OPENAI_COMPAT_MODEL", "meta/llama-3.3-70b-instruct")
    monkeypatch.setattr(settings, "OPENAI_COMPAT_EMBED_MODEL", "")
    monkeypatch.setattr(settings, "OPENAI_COMPAT_LABEL", "")
    monkeypatch.setattr(oc, "_under_pytest", lambda: False)
    monkeypatch.setattr(oc, "_json_mode_ok", None)
    monkeypatch.setattr(oc, "_tools_ok", None)
    monkeypatch.setattr(oc.time, "sleep", lambda s: None)
    monkeypatch.setattr(llm_client, "_local_cache", {})
    yield monkeypatch


def use(monkeypatch, api: FakeAPI) -> FakeAPI:
    monkeypatch.setattr(oc, "_httpx_post", api)
    return api


def test_defaults_and_gating(monkeypatch):
    fields = Settings.model_fields
    assert (fields["LLM_PROVIDER"].default or "") == ""
    assert fields["OPENAI_COMPAT_BASE_URL"].default == "https://integrate.api.nvidia.com/v1"
    assert fields["OPENAI_COMPAT_MODEL"].default == "meta/llama-3.3-70b-instruct"
    assert fields["OPENAI_COMPAT_API_KEY"].default == ""
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai_compat")
    monkeypatch.setattr(settings, "OPENAI_COMPAT_API_KEY", FAKE_KEY)
    monkeypatch.setattr(settings, "AI_MODE", "auto")
    assert not oc.enabled()  # under pytest
    assert oc.enabled(allow_in_tests=True)
    for mode in ("replay", "fallback"):
        monkeypatch.setattr(settings, "AI_MODE", mode)
        assert not oc.enabled(allow_in_tests=True)
    monkeypatch.setattr(settings, "AI_MODE", "auto")
    monkeypatch.setattr(settings, "OPENAI_COMPAT_API_KEY", "replace-me")
    assert not oc.enabled(allow_in_tests=True)
    monkeypatch.setattr(settings, "OPENAI_COMPAT_BASE_URL", "http://127.0.0.1:11434/v1")
    assert oc.enabled(allow_in_tests=True)  # a local server needs no key
    assert oc.label() == "Test model (local)"


def test_label_is_honest(nim):
    assert oc.label() == "Test model (NVIDIA)"
    assert display_name("openai_compat") == "Test model (NVIDIA)"
    assert "Gemini" not in display_name("openai_compat")
    assert AiCall(provider="openai_compat", cached=True).badge() == "test"
    row = _trace_step("Intake", "complete", "s", "o", [], 0.0, provider="openai_compat", model="meta/llama-3.3-70b-instruct")
    assert row["provider_label"] == "Test model (NVIDIA)" and row["vendor"] == "NVIDIA"
    nim.setattr(settings, "OPENAI_COMPAT_LABEL", "NIM staging")
    assert oc.label() == "Test model (NIM staging)"


def test_intake_is_one_json_call_with_bearer_key_and_cached_by_text(nim):
    api = use(nim, FakeAPI(chat("```json\n" + json.dumps(INTAKE, ensure_ascii=False) + "\n```", tokens=321)))
    text = f"5 people stuck near Gandhi School ward 4, water rising {uuid.uuid4().hex[:6]}"
    out = IntakeAgent().parse_report(text, language_hint="en")
    assert out.type.value == "rescue" and out.text_en.startswith("Five people")
    assert out.text_hi and out.translation_confidence == 0.92
    usage = llm_client.last_ai
    assert usage.provider == "openai_compat" and usage.model == "meta/llama-3.3-70b-instruct" and usage.tokens == 321
    assert len(api.calls) == 1
    call = api.calls[0]
    assert call["url"] == "https://integrate.api.nvidia.com/v1/chat/completions"
    assert call["headers"]["Authorization"] == f"Bearer {FAKE_KEY}"
    assert call["json"]["response_format"] == {"type": "json_object"}
    assert call["json"]["model"] == "meta/llama-3.3-70b-instruct"
    assert "<report>" in call["json"]["messages"][1]["content"]
    IntakeAgent().parse_report(text, language_hint="en")
    assert len(api.calls) == 1 and llm_client.last_ai.cached and llm_client.last_ai.provider == "openai_compat"


def test_server_without_json_mode_is_asked_again_without_it(nim):
    api = use(nim, FakeAPI(_Resp(400, {"error": "response_format is not supported"}), chat(json.dumps(INTAKE))))
    out = IntakeAgent().parse_report(f"5 people stuck at Gandhi School {uuid.uuid4().hex[:6]}")
    assert out.type.value == "rescue"
    assert "response_format" in api.calls[0]["json"] and "response_format" not in api.calls[1]["json"]
    assert oc._json_mode_ok is False


def test_invalid_json_gets_one_repair_then_rules(nim):
    api = use(nim, FakeAPI(chat("not json"), chat(json.dumps(INTAKE))))
    out = IntakeAgent().parse_report(f"5 people stuck at Gandhi School {uuid.uuid4().hex[:6]}")
    assert out.type.value == "rescue" and llm_client.last_ai.provider == "openai_compat"
    assert "PREVIOUS OUTPUT WAS INVALID" in api.calls[1]["json"]["messages"][1]["content"]

    use(nim, FakeAPI(chat('{"type": "flying_saucer"}')))
    IntakeAgent().parse_report(f"5 people stuck at Gandhi School {uuid.uuid4().hex[:6]}")
    assert llm_client.last_ai.provider == "fallback" and llm_client.last_ai.fallback_reason == "invalid_json"


def test_http_errors_fall_back_without_leaking_the_key(nim, caplog):
    use(nim, FakeAPI(_Resp(429, "Too Many Requests")))
    IntakeAgent().parse_report(f"5 people stuck at Gandhi School {uuid.uuid4().hex[:6]}")
    assert llm_client.last_ai.provider == "fallback" and llm_client.last_ai.fallback_reason == "quota"
    api = use(nim, FakeAPI(_Resp(503, "busy"), chat(json.dumps(INTAKE))))
    IntakeAgent().parse_report(f"5 people stuck at Gandhi School {uuid.uuid4().hex[:6]}")
    assert llm_client.last_ai.provider == "openai_compat" and len(api.calls) == 2
    assert FAKE_KEY not in caplog.text


def test_ask_the_desk_uses_a_forced_tool_call(nim):
    args = {"types": ["rescue"], "ward_ids": ["ward_4"], "vulnerable": ["elderly"], "waiting_only": True,
            "reason": "Waiting rescue cases with elderly people in ward 4."}
    api = use(nim, FakeAPI(chat(None, tool_args=args)))
    question = f"which elderly rescue cases in ward 4 are still waiting? {uuid.uuid4().hex[:6]}"
    answer = desk_query.ask(question, [])
    body = api.calls[0]["json"]
    assert body["tools"][0]["function"]["name"] == "search_cases"
    assert body["tool_choice"] == {"type": "function", "function": {"name": "search_cases"}}
    assert answer["ai"]["provider"] == "openai_compat" and answer["ai"]["mode"] == "tool"
    assert answer["ai"]["vendor"] == "NVIDIA" and answer["filters"]["ward_ids"] == ["ward_4"]
    row = answer["trace"][0]
    assert row["provider_label"] == "Test model (NVIDIA)" and "Gemini" not in json.dumps(answer["trace"])
    desk_query.ask(question, [])
    assert len(api.calls) == 1


def test_ask_the_desk_emulates_tools_with_json(nim):
    args = {"types": ["food"], "waiting_only": False, "reason": "Food cases."}
    api = use(nim, FakeAPI(_Resp(400, {"error": "tools not supported"}), chat(json.dumps(args))))
    answer = desk_query.ask(f"food cases {uuid.uuid4().hex[:6]}", [])
    assert answer["ai"]["mode"] == "json" and answer["filters"]["types"] == ["food"]
    second = api.calls[1]["json"]
    assert "tools" not in second and "search_cases arguments" in second["messages"][1]["content"]
    assert oc._tools_ok is False


def test_ask_the_desk_falls_back_to_rules_on_error(nim):
    use(nim, FakeAPI(_Resp(500, "down")))
    answer = desk_query.ask(f"food cases {uuid.uuid4().hex[:6]}", [])
    assert answer["ai"]["provider"] == "fallback" and answer["filters"]["types"] == ["food"]
    assert answer["trace"][0]["provider_label"] == "Rules"


def test_embeddings_use_nim_only_when_configured(nim):
    api = use(nim, FakeAPI(_Resp(200, {"data": []})))
    assert embeddings.embed_texts(["a", "b"]) is None
    assert api.calls == []
    assert "Gemini" not in embeddings.describe()

    nim.setattr(settings, "OPENAI_COMPAT_EMBED_MODEL", "nvidia/llama-3.2-nv-embedqa-1b-v2")
    api = use(nim, FakeAPI(_Resp(200, {"data": [{"index": 1, "embedding": [0.0, 2.0]}, {"index": 0, "embedding": [3.0, 4.0]}]})))
    vectors = embeddings.embed_texts(["first", "second"])
    assert vectors == [[0.6, 0.8], [0.0, 1.0]]
    call = api.calls[0]
    assert call["url"].endswith("/v1/embeddings") and call["json"]["input_type"] == "query"
    assert call["json"]["model"] == "nvidia/llama-3.2-nv-embedqa-1b-v2"
    assert embeddings.describe().startswith("nvidia/llama-3.2-nv-embedqa-1b-v2 via Test model (NVIDIA)")

    use(nim, FakeAPI(_Resp(500, "down")))
    assert embeddings.embed_texts(["first", "second"]) is None


def test_test_provider_never_calls_gemini_embeddings(nim):
    nim.setattr(settings, "GEMINI_API_KEY", "real-looking-gemini-key")
    nim.setattr(settings, "GEMINI_ENABLED", True)

    def no_gemini(*a, **k):
        raise AssertionError("Gemini embeddings must not run under openai_compat")

    nim.setattr("google.genai.Client", no_gemini)
    assert embeddings.embed_texts(["a"]) is None


def test_bench_and_record_are_gemini_only(nim):
    from bench.gemini_eval import evaluate_gemini

    with pytest.raises(RuntimeError, match="allow-test-provider"):
        assert_gemini_only("benchmark")
    with pytest.raises(RuntimeError):
        evaluate_gemini([{"id": "m1", "text": "x"}], {}, "2026-10-13", extract=lambda t, l: {"type": "rescue"})
    blank = evaluate_gemini([{"id": "m1", "text": "x"}], {}, "2026-10-13",
                            extract=lambda t, l: {"type": "rescue"}, allow_test_provider=True)
    assert blank["measured"] is False and blank["reason"] == "test_provider"
    with pytest.raises(RuntimeError, match="record-ai"):
        from app.llm.record import record_seeded_reports

        record_seeded_reports()


def test_run_benchmark_refuses_without_the_flag(nim, tmp_path):
    from bench.run_bench import run_benchmark

    with pytest.raises(SystemExit, match="openai_compat"):
        run_benchmark(Path("does-not-matter"), out_dir=tmp_path)


def test_health_names_the_test_provider(nim):
    body = TestClient(app).get("/api/health/ai").json()
    assert body["provider"] == "openai_compat" and body["label"] == "Test model (NVIDIA)"
    assert body["model"] == "meta/llama-3.3-70b-instruct" and FAKE_KEY not in json.dumps(body)


def test_submitted_report_trace_says_test_model(nim, tmp_path):
    nim.setattr(settings, "DEMO_MODE", False)
    nim.setattr("app.llm.client.CACHE_DIR", tmp_path)
    nim.setattr("app.agents.pipeline._spawn", _start_thread)
    nim.setattr("app.agents.dedupe.dedupe_agent.embedder", lambda texts: None)
    use(nim, FakeAPI(chat(json.dumps(INTAKE, ensure_ascii=False))))
    token = uuid.uuid4().hex[:8]
    text = f"5 people stuck near Gandhi School ward 4, water rising {token}"
    res = TestClient(app).post("/api/reports", json={
        "text": text, "raw_text": text, "lang": "en", "channel": "text",
        "location_pin": {"lat": 8.9, "lng": 77.9}, "idempotency_key": f"oc-{token}", "source_id": f"oc-{token}",
    })
    assert res.status_code == 200, res.text
    try:
        assert wait_for_idle(10.0)
        rid = res.json()["request_id"]
        req = storage_service.get_request(rid)
        target = storage_service.get_request(req.merged_into) if req.merged_into else req
        assert target.ai.provider == "openai_compat" and target.ai_source == "openai_compat"
        intake = next(row for row in target.trace if row["agent"] == "Intake")
        assert intake["provider"] == "openai_compat" and intake["provider_label"] == "Test model (NVIDIA)"
        assert intake["model"] == "meta/llama-3.3-70b-instruct"
        assert target.analysis["provider"] == "openai_compat"
        assert "Gemini" not in json.dumps([row.get("provider_label") for row in target.trace])
    finally:
        # The recent-reports list shows the newest 20; leave the shared store as it was.
        for report_id in [k for k, v in storage_service._reports.items() if token in (v.raw_text or "")]:
            storage_service._reports.pop(report_id, None)
        for request_id in [k for k, v in storage_service._requests.items() if token in (v.raw_text or "")]:
            storage_service._requests.pop(request_id, None)
