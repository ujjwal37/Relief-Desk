"""Water depth from the model's reading of a report, used to pick boat vs ground team.

The band only counts when the model quotes words that really appear in the report.
Otherwise it is "unknown" and matching keeps its usual behaviour.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

BANDS = ("none", "ankle", "knee", "waist", "chest", "roof", "unknown")
SHALLOW = {"none", "ankle", "knee"}
DEEP = {"waist", "chest", "roof"}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def validate_depth(band: Optional[str], quote: Optional[str], raw_text: str, source: str) -> Optional[Dict[str, Any]]:
    """Keep the band only with a real quote from the report. None when nothing usable."""
    band = (band or "").strip().lower()
    if band not in BANDS or band == "unknown":
        return None
    q = (quote or "").strip()
    if not q or _norm(q) not in _norm(raw_text):
        return {"band": "unknown", "quote": None, "source": source}
    return {"band": band, "quote": q[:200], "source": source}


def band_of(request: Any) -> str:
    depth = getattr(request, "water_depth", None) or {}
    band = depth.get("band") if isinstance(depth, dict) else None
    return band if band in BANDS else "unknown"


def depth_rank(request: Any, resource: Any) -> int:
    """0 = preferred for this depth, 1 = less suited. Unknown depth changes nothing."""
    band = band_of(request)
    kind = getattr(getattr(resource, "kind", None), "value", getattr(resource, "kind", None))
    is_boat = kind == "boat"
    if band in DEEP:
        return 0 if is_boat else 1
    if band in SHALLOW:
        return 1 if is_boat else 0
    return 0


_RULES = [
    ("roof", r"(?:on|onto|to) (?:the |our |a )?(?:roof|terrace|rooftop)|\btrapped on (?:the )?terrace\b|छत पर|മേൽക്കൂര|terrace-il|terrace il"),
    ("roof", r"water (?:up )?to (?:the )?(?:first|upper|second) floor|first floor (?:is |was )?(?:under|flooded|submerged)|पहली मंजिल तक"),
    ("chest", r"chest[- ]deep|up to (?:our |my |the )?(?:chest|neck)|neck[- ]deep|छाती तक|सीने तक|नेक तक|nenju vare|നെഞ്ച്"),
    ("waist", r"waist[- ]deep|up to (?:our |my |the )?waist|कमर तक|aravattam|അരയോളം|at the windows?|window level"),
    ("waist", r"\b(?:on|in) (?:the )?(?:first|upper) floor\b|first floor il|first floor-il"),
    ("knee", r"knee[- ]deep|up to (?:our |my |the )?knees?|घुटने तक|മുട്ടോളം"),
    ("ankle", r"ankle[- ]deep|up to (?:our |my |the )?ankles?|टखने तक"),
]


def depth_from_text(raw_text: str) -> Optional[Dict[str, Any]]:
    """Rules reading of water depth. The quote is the exact words found in the report."""
    text = raw_text or ""
    for band, pattern in _RULES:
        m = re.search(pattern, text, re.I)
        if m:
            return {"band": band, "quote": text[m.start():m.end()], "source": "rules"}
    return None


def fill_depth(request: Any) -> None:
    """Keep a quoted model band; otherwise read the report words. Unknown stays unknown."""
    if band_of(request) != "unknown":
        return
    texts = [getattr(request, "raw_text", None) or ""]
    for q in getattr(request, "report_quotes", None) or []:
        texts.append(getattr(q, "text", "") or "")
    texts.append(getattr(request, "place_text", None) or "")
    for t in texts:
        got = depth_from_text(t)
        if got:
            request.water_depth = got
            return
