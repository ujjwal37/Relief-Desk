"""Record real Gemini replies for the seeded flood reports.

`make record-ai` is the only writer. It exits before any file is created when
GEMINI_API_KEY is missing or a placeholder. Fallback text is never stored.
"""
from __future__ import annotations

import json
import os
import time
import sys

from app.config import settings

PLACEHOLDER_KEYS = {"", "replace-me", "synthetic-demo-gemini-key"}


def require_real_key(key: str) -> str:
    cleaned = (key or "").strip()
    if cleaned in PLACEHOLDER_KEYS:
        raise SystemExit(
            "record-ai needs a real GEMINI_API_KEY. No file was written to data/ai_cache."
        )
    return cleaned


def _never_antigravity() -> None:
    """data/ai_cache holds Gemini API replies only: no test provider, with or without a flag."""
    from app.llm.providers import assert_gemini_only

    assert_gemini_only("record-ai")


def record_seeded_reports() -> int:
    """Call Gemini for each seeded report and write data/ai_cache/{hash}.json."""
    _never_antigravity()
    from app.agents.intake import SYSTEM_INTAKE_PROMPT, intake_user_prompt
    from app.llm.client import REPLAY_DIR, llm_client
    from app.models.schemas import ExtractedRequest
    key = require_real_key(os.environ.get("GEMINI_API_KEY") or settings.GEMINI_API_KEY)
    settings.GEMINI_API_KEY = key
    settings.GEMINI_ENABLED = True
    settings.AI_MODE = "auto"
    REPLAY_DIR.mkdir(parents=True, exist_ok=True)

    def _valid(text: str) -> ExtractedRequest:
        clean = text.strip()
        if clean.startswith("```json"):
            clean = clean[7:]
        elif clean.startswith("```"):
            clean = clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
        parsed = json.loads(clean.strip())
        return ExtractedRequest(**parsed)

    written = 0
    kept = 0
    # Free-tier flash-lite allows 15 requests a minute. Stay under it.
    gap_s = float(os.environ.get("RECORD_AI_GAP_S", "4.5"))
    from app.llm.replay_catalog import catalog_rows

    rows = [
        {"id": row["id"], "prompt": intake_user_prompt(row["text"] or "", row.get("lang"))}
        for row in catalog_rows()
    ]
    for row in rows:
        user_prompt = row["prompt"]
        digest = llm_client.cache_key(SYSTEM_INTAKE_PROMPT, user_prompt)
        if (REPLAY_DIR / f"{digest}.json").exists():
            kept += 1
            continue
        if written:
            time.sleep(gap_s)
        text = llm_client.generate_content(
            system_instruction=SYSTEM_INTAKE_PROMPT,
            user_prompt=user_prompt,
            validator=_valid,
            max_retries=1,
        )
        if llm_client.last_ai.provider != "gemini":
            print(
                f"skip {row['id']}: {llm_client.last_ai.fallback_reason or llm_client.last_ai.provider}",
                file=sys.stderr,
            )
            continue
        digest = llm_client.cache_key(SYSTEM_INTAKE_PROMPT, user_prompt)
        payload = {
            "key": digest,
            "response": text,
            "source": "gemini",
            "provider": "gemini",
            "model": llm_client.last_ai.model,
            "tokens": llm_client.last_ai.tokens,
            "report_id": row["id"],
        }
        (REPLAY_DIR / f"{digest}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        written += 1
        print(f"recorded {row['id']} -> {digest[:8]}")

    if written == 0 and kept == 0:
        raise SystemExit(
            "Gemini returned no usable replies. Fallback text was not written to data/ai_cache."
        )
    print(f"Wrote {written} new recorded Gemini replies ({kept} already recorded) to {REPLAY_DIR}")
    return written
