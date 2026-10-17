"""Mark seeded demo cases whose intake reading was recorded from a real Gemini call."""
from __future__ import annotations

import hashlib
import json
import logging

from app.models.schemas import AiCall

logger = logging.getLogger("relief_desk.replay_seed")


def seed_prompt(raw_text: str) -> str:
    from app.agents.intake import intake_user_prompt

    return intake_user_prompt(raw_text or "", None)


def trace_fingerprint(req) -> str:
    facts = {"raw": req.raw_text, "type": req.type.value, "people": req.people_count,
             "vulnerable": req.vulnerable.model_dump(), "hazard": req.hazard.value,
             "lat": req.lat, "lng": req.lng}
    return hashlib.sha256(json.dumps(facts, sort_keys=True).encode()).hexdigest()


def attach_recorded_ai(storage) -> int:
    """Seeded cases with a file in data/ai_cache show "Recorded (Gemini)" instead of the fallback.

    Only the provenance is attached: the stored reply came from a real Gemini call made by
    `make record-ai`. Cases without a recording keep their offline-fallback label.
    """
    from app.agents.intake import SYSTEM_INTAKE_PROMPT
    from app.llm import client as llm

    attached = 0
    replay_traces = list(llm.REPLAY_DIR.glob("*.trace.json")) if llm.REPLAY_DIR.exists() else []
    for req in list(storage._requests.values()):
        if req.ai is not None and req.ai.provider in ("gemini", "cache"):
            continue
        key = llm.llm_client.cache_key(SYSTEM_INTAKE_PROMPT, seed_prompt(req.raw_text))
        path = llm.REPLAY_DIR / f"{key}.json"
        trace_path = llm.REPLAY_DIR / f"{key}.trace.json"

        # Fallback to matching by fingerprint or input summary if prompt hash changed
        if not path.exists():
            fp = trace_fingerprint(req)
            matched_trace = None
            for tp in replay_traces:
                try:
                    data = json.loads(tp.read_text(encoding="utf-8"))
                    if data.get("fingerprint") == fp:
                        matched_trace = tp
                        break
                    intake = (data.get("trace") or [{}])[0]
                    if intake.get("input_summary") and intake["input_summary"] == req.raw_text:
                        matched_trace = tp
                        break
                except (OSError, ValueError):
                    continue
            if matched_trace:
                trace_path = matched_trace
                base_name = matched_trace.name.replace(".trace.json", ".json")
                path = matched_trace.parent / base_name

        if not path.exists():
            continue
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if meta.get("provider", meta.get("source")) not in ("gemini", "cache"):
            continue
        req.ai = AiCall(provider="cache", model=meta.get("model", "gemini-3.5-flash-lite"), tokens=meta.get("tokens"), cached=True)
        req.ai_source = "recorded"
        if trace_path.exists():
            try:
                recording = json.loads(trace_path.read_text(encoding="utf-8"))
                trace = recording.get("trace") or []
                if len(trace) == 5 and all(row.get("provider") in ("gemini", "cache", "tool") for row in trace):
                    req.trace = [{**row, "provider": "cache" if row.get("provider") in ("gemini", "cache") else "tool",
                                  "recorded_at": recording.get("recorded_at")} for row in trace]
                    req.analysis = recording.get("analysis") or {}
            except (OSError, ValueError, TypeError):
                logger.warning("Ignoring invalid trace recording for %s", req.id)
        attached += 1
    if attached:
        logger.info("Attached %d recorded Gemini readings to seeded cases.", attached)
    return attached
