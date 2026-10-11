"""Score Gemini against the frozen split. No key means the column is not measured."""
import json
import time
from typing import Any, Callable, Dict, List, Optional

from app.config import settings
from app.llm.client import llm_client


class TokenBucket:
    """Spaces live calls. Tests pass a fake clock and a fake sleep."""

    def __init__(self, per_minute: float = 30.0, sleep=time.sleep, now=time.monotonic):
        if per_minute <= 0:
            raise ValueError("per_minute must be positive")
        self.gap = 60.0 / per_minute
        self.sleep = sleep
        self.now = now
        self._next = 0.0

    def wait(self) -> None:
        current = self.now()
        if current < self._next:
            self.sleep(self._next - current)
            current = self._next
        self._next = current + self.gap


def blank(reason: str, n: int, date: str) -> Dict[str, Any]:
    return {
        "measured": False,
        "reason": reason,
        "model": settings.GEMINI_MODEL,
        "date": date,
        "n": n,
        "cache": True,
        "rate_limit_per_min": 30,
        "type_accuracy_pct": None,
        "place_ward_accuracy_pct": None,
        "calls": 0,
    }


def _offline_reason() -> str:
    mode = (settings.AI_MODE or "auto").lower()
    if mode == "fallback" or not settings.GEMINI_ENABLED:
        return "disabled"
    return "no_api_key"


def score_pairs(rows: List[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    type_n = type_hit = ward_n = ward_hit = 0
    for row in rows:
        if row.get("gold_type"):
            type_n += 1
            if row.get("pred_type") == row["gold_type"]:
                type_hit += 1
        if row.get("gold_ward"):
            ward_n += 1
            if row.get("pred_ward") == row["gold_ward"]:
                ward_hit += 1

    def pct(hit: int, total: int) -> Optional[float]:
        if total <= 0:
            return None
        return round(100.0 * hit / total, 1)

    return {
        "type_accuracy_pct": pct(type_hit, type_n),
        "place_ward_accuracy_pct": pct(ward_hit, ward_n),
        "type_n": type_n,
        "ward_n": ward_n,
    }


def evaluate_gemini(
    messages: List[Dict[str, Any]],
    labels: Dict[str, Dict[str, Any]],
    date: str,
    extract: Optional[Callable[[str, Optional[str]], Optional[Dict[str, Any]]]] = None,
    bucket: Optional[TokenBucket] = None,
) -> Dict[str, Any]:
    """Rate-limited Gemini reads. A missing key does not invent a score."""
    count = len(messages)
    if extract is None and not llm_client.gemini_live():
        return blank(_offline_reason(), count, date)

    bucket = bucket or TokenBucket(30)
    extract = extract or live_extract
    rows: List[Dict[str, Any]] = []
    calls = 0
    fallbacks = 0
    for msg in messages:
        bucket.wait()
        calls += 1
        pred = extract(msg["text"], msg.get("lang"))
        if pred is None:
            fallbacks += 1
            pred = {"type": None, "ward_id": None}
        ground = labels.get(msg["id"], {}).get("ground_truth", {})
        rows.append({
            "gold_type": ground.get("type"),
            "pred_type": pred.get("type"),
            "gold_ward": ground.get("ward_id"),
            "pred_ward": pred.get("ward_id"),
        })
    if calls and fallbacks == calls:
        missed = blank("fallback", count, date)
        missed["calls"] = calls
        return missed
    scored = score_pairs(rows)
    return {
        "measured": True,
        "reason": None,
        "model": settings.GEMINI_MODEL,
        "date": date,
        "n": count,
        "cache": True,
        "rate_limit_per_min": 30,
        "calls": calls,
        "fallback_skipped": fallbacks,
        **scored,
    }


def live_extract(text: str, lang: Optional[str]) -> Optional[Dict[str, Any]]:
    """One cached Gemini read. Rule repair does not replace the model's type."""
    from app.agents.intake import SYSTEM_INTAKE_PROMPT
    from app.models.schemas import ExtractedRequest
    from app.tools.gazetteer import gazetteer

    user_prompt = f"<report>\n{text.strip()}\n</report>"
    if lang:
        user_prompt += f"\n\nLanguage hint: {lang}"

    def validate(text_output: str) -> ExtractedRequest:
        clean = text_output.strip()
        if clean.startswith("```json"):
            clean = clean[7:]
        elif clean.startswith("```"):
            clean = clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
        return ExtractedRequest(**json.loads(clean.strip()))

    raw = llm_client.generate_content(
        system_instruction=SYSTEM_INTAKE_PROMPT,
        user_prompt=user_prompt,
        validator=validate,
        max_retries=1,
    )
    usage = llm_client.last_ai
    if usage is None or usage.provider not in ("gemini", "cache"):
        return None
    parsed = validate(raw)
    found = gazetteer.lookup(parsed.place_text or "")
    ward = found.ward_id if found.ward_id and not found.is_low_confidence else None
    return {"type": parsed.type.value, "ward_id": ward}
