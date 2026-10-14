"""Mark seeded demo cases whose intake reading was recorded from a real Gemini call."""
from __future__ import annotations

import json
import logging

from app.models.schemas import AiCall

logger = logging.getLogger("relief_desk.replay_seed")


def seed_prompt(raw_text: str) -> str:
    from app.agents.intake import intake_user_prompt

    return intake_user_prompt(raw_text or "", None)


def attach_recorded_ai(storage) -> int:
    """Seeded cases with a file in data/ai_cache show "Recorded (Gemini)" instead of the fallback.

    Only the provenance is attached: the stored reply came from a real Gemini call made by
    `make record-ai`. Cases without a recording keep their offline-fallback label.
    """
    from app.agents.intake import SYSTEM_INTAKE_PROMPT
    from app.llm import client as llm

    attached = 0
    for req in list(storage._requests.values()):
        if req.ai is not None and req.ai.provider in ("gemini", "cache"):
            continue
        key = llm.llm_client.cache_key(SYSTEM_INTAKE_PROMPT, seed_prompt(req.raw_text))
        path = llm.REPLAY_DIR / f"{key}.json"
        if not path.exists():
            continue
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if meta.get("provider", meta.get("source")) not in ("gemini", "cache"):
            continue
        req.ai = AiCall(provider="cache", model=meta.get("model"), tokens=meta.get("tokens"), cached=True)
        req.ai_source = "recorded"
        attached += 1
    if attached:
        logger.info("Attached %d recorded Gemini readings to seeded cases.", attached)
    return attached
