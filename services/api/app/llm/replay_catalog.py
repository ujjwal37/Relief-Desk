"""Prompts `make record-ai` fills later. This module stores no model replies.

The committed fixture lists the same ids with a null response. Replay serves a
hash file only after a real Gemini call writes one. Until then a catalog prompt
uses the deterministic fallback and does not call Gemini.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

# Stable lines from the scripted phone checks. The live specs append a unique tag,
# so those exact runs are not in the fixture. The sentences below are what record-ai fills.
SCRIPTED_PHONE_REPORTS = (
    {
        "id": "phone-kainakary-merge",
        "lang": "en",
        "text": "Another report from Kainakary Ferry, water still rising",
    },
    {
        "id": "phone-hindi-ward12",
        "lang": "hi",
        "text": "वार्ड 12 में 6 लोग फंसे हैं, एक बच्चा भी है, पानी बढ़ रहा है, नाव भेजो।",
    },
)

_KEYS: Optional[set] = None


def catalog_rows() -> List[Dict[str, Optional[str]]]:
    """Demo-pack reports, seeded desk lines, and the scripted phone sentences."""
    import yaml

    from app.tools.demo_seed import build_demo_reports

    rows: List[Dict[str, Optional[str]]] = []
    seen = set()

    def add(row_id: str, text: Optional[str], lang: Optional[str]) -> None:
        clean = (text or "").strip()
        if not clean or clean in seen:
            return
        seen.add(clean)
        rows.append({"id": row_id, "text": clean, "lang": lang})

    for report in build_demo_reports():
        add(str(report["id"]), report.get("text"), report.get("lang"))

    path = Path(__file__).resolve().parents[4] / "data" / "synthetic" / "flood_v1" / "seeds.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    for item in data.get("incidents") or []:
        samples = {
            sample.get("lang"): sample.get("text")
            for sample in item.get("sample_reports") or []
            if sample.get("lang") and sample.get("text")
        }
        # Same line the desk stores. attach_recorded_ai hashes it with no language hint.
        raw = samples.get("hi") if item.get("id") == "INC-001" and samples.get("hi") else samples.get("en")
        add(str(item.get("id")), raw, None)

    for report in SCRIPTED_PHONE_REPORTS:
        add(report["id"], report["text"], report["lang"])
    return rows


def catalog_keys() -> set:
    """Cache keys for the catalog prompts. A hit means replay must not call Gemini."""
    global _KEYS
    if _KEYS is not None:
        return _KEYS
    from app.agents.intake import SYSTEM_INTAKE_PROMPT, intake_user_prompt
    from app.llm.client import llm_client

    _KEYS = {
        llm_client.cache_key(SYSTEM_INTAKE_PROMPT, intake_user_prompt(row["text"] or "", row.get("lang")))
        for row in catalog_rows()
    }
    return _KEYS
