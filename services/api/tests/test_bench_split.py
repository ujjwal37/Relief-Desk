"""The held-out ids stay frozen, and Gemini is not scored without a key."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "api"))

from bench.gemini_eval import TokenBucket, evaluate_gemini, score_pairs
from bench.run_bench import load_split, messages_for_split

DATA = ROOT / "data" / "synthetic" / "flood_v1"


def _messages():
    return [json.loads(line) for line in (DATA / "messages.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]


def test_corpus_has_at_least_300_labelled_reports_and_a_frozen_test():
    messages = _messages()
    labels = [json.loads(line) for line in (DATA / "labels.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(messages) >= 300
    assert {row["id"] for row in messages} == {row["message_id"] for row in labels}
    langs = {row["lang"] for row in messages}
    assert {"en", "hi", "hinglish"} <= langs
    assert "ta" not in langs
    meta = load_split(DATA)
    assert meta["seed"] == 42
    assert meta["test_ids"][0] == "MSG-0073"
    assert meta["test_ids"][-1] == "MSG-0240"
    assert len(meta["test_ids"]) == 168
    assert len(meta["dev_ids"]) == 72
    test_rows = messages_for_split(messages, meta, "test")
    train_rows = messages_for_split(messages, meta, "train")
    assert [row["id"] for row in test_rows] == meta["test_ids"]
    assert all(row["id"] not in set(meta["test_ids"]) for row in train_rows)
    assert len(train_rows) == len(messages) - 168 - 72


def test_gemini_column_stays_empty_without_a_key(monkeypatch):
    monkeypatch.setattr("bench.gemini_eval.llm_client.gemini_live", lambda: False)
    monkeypatch.setattr("bench.gemini_eval.settings.GEMINI_ENABLED", True)
    monkeypatch.setattr("bench.gemini_eval.settings.AI_MODE", "auto")
    result = evaluate_gemini([{"id": "MSG-1", "text": "boat", "lang": "en"}], {}, "2026-10-12")
    assert result["measured"] is False
    assert result["reason"] == "no_api_key"
    assert result["type_accuracy_pct"] is None
    assert result["model"]


def test_mocked_gemini_scores_are_counted_and_rate_limited():
    calls = {"n": 0}

    def extract(text, lang):
        calls["n"] += 1
        return {"type": "rescue", "ward_id": "ward_2"}

    slept = []
    bucket = TokenBucket(per_minute=30, sleep=lambda seconds: slept.append(seconds), now=lambda: 0.0)
    labels = {
        "A": {"ground_truth": {"type": "rescue", "ward_id": "ward_2"}},
        "B": {"ground_truth": {"type": "medical", "ward_id": "ward_1"}},
    }
    messages = [
        {"id": "A", "text": "boat", "lang": "en"},
        {"id": "B", "text": "dawai", "lang": "hi"},
    ]
    result = evaluate_gemini(messages, labels, "2026-10-12", extract=extract, bucket=bucket)
    assert calls["n"] == 2
    assert slept == [2.0]
    assert result["measured"] is True
    assert result["type_accuracy_pct"] == 50.0
    assert result["place_ward_accuracy_pct"] == 50.0
    assert result["cache"] is True
    scored = score_pairs([
        {"gold_type": "rescue", "pred_type": "rescue", "gold_ward": "ward_1", "pred_ward": "ward_1"},
    ])
    assert scored["type_accuracy_pct"] == 100.0

def test_gemini_eval_stops_on_quota_and_scores_only_answered():
    from bench.gemini_eval import TokenBucket, evaluate_gemini

    msgs = [{"id": f"M{i}", "text": "t"} for i in range(6)]
    labels = {f"M{i}": {"ground_truth": {"type": "food"}} for i in range(6)}
    answers = iter([{"type": "food", "ward_id": None}, {"type": "rescue", "ward_id": None}, None, None, None, {"type": "food"}])
    out = evaluate_gemini(msgs, labels, "2026-10-12", extract=lambda t, l: next(answers),
                          bucket=TokenBucket(60, sleep=lambda s: None, now=lambda: 0.0), rpm=14)
    assert out["measured"] and out["stopped_early"]
    assert out["n"] == 2 and out["n_planned"] == 6
    assert out["type_accuracy_pct"] == 50.0
    assert out["rate_limit_per_min"] == 14


def test_gemini_eval_reports_type_by_label_kind():
    from bench.gemini_eval import TokenBucket, evaluate_gemini

    msgs = [{"id": "S1", "text": "a"}, {"id": "D1", "text": "b"}]
    labels = {"S1": {"label_type": "single_incident", "ground_truth": {"type": "food"}},
              "D1": {"label_type": "duplicate_of", "ground_truth": {"type": "medical"}}}
    out = evaluate_gemini(msgs, labels, "d", extract=lambda t, l: {"type": "food", "ward_id": None},
                          bucket=TokenBucket(60, sleep=lambda s: None, now=lambda: 0.0))
    assert out["type_accuracy_pct"] == 50.0
    assert out["type_accuracy_need_stated_pct"] == 100.0
    assert out["type_by_label_type"]["duplicate_of"]["type_accuracy_pct"] == 0.0
