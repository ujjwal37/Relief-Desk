"""Water depth from the model's reading of a report, used to pick boat vs ground team.

The band only counts when the model quotes words that really appear in the report.
Otherwise it is "unknown" and matching keeps its usual behaviour.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

BANDS = ("none", "ankle", "knee", "waist", "chest", "floor", "roof", "unknown")
SHALLOW = {"none", "ankle", "knee"}
DEEP = {"waist", "chest", "floor", "roof"}
# Where people are standing. That is not a water level.
_POSITION = re.compile(
    r"(?:on|onto|in|at)\s+(?:the\s+|our\s+|a\s+)?(?:roof|rooftop|terrace|first floor|upper floor)"
    r"|छत पर|terrace[- ]?il|first floor[- ]?il|ഒന്നാം നിലയിൽ|മേൽക്കൂരയിൽ",
    re.I,
)


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
    # "छत पर" / "on the roof" says where people are. It is not "up to the roof".
    if _POSITION.search(q) and not re.search(r"water|flood|deep|submerged|पानी|വെള്ളം", q, flags=re.I):
        return {"band": "unknown", "quote": None, "source": source}
    if band == "roof" and not _water_at_roof(q):
        return {"band": "unknown", "quote": None, "source": source}
    return {"band": band, "quote": q[:200], "source": source}


def _water_at_roof(quote: str) -> bool:
    """Roof depth is only water reaching the roof, never where the people are."""
    if re.search(r"first\s*floor|पहली मंजिल|ഒന്നാം നില", quote or "", flags=re.I):
        return False
    has_water = re.search(r"water|flood|deep|पानी|വെള്ളം", quote or "", flags=re.I)
    has_roof = re.search(r"roof|terrace|rooftop|छत|മേൽക്കൂര", quote or "", flags=re.I)
    return bool(has_water and has_roof)


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
    ("roof", r"water (?:is |was )?(?:up |over )?(?:to )?(?:the )?(?:roof|terrace|rooftop)|(?:roof|terrace)[- ]deep|छत तक(?: पानी)?|വെള്ളം.{0,16}മേൽക്കൂര"),
    ("floor", r"water (?:up )?to (?:the )?(?:first|upper|second) floor|first floor (?:is |was )?(?:under|flooded|submerged)|पहली मंजिल तक"),
    ("floor", r"ground floor (?:is |was |fully )?(?:under(?: water)?|flooded|submerged|drowned)|house (?:is )?(?:fully )?submerged"),
    ("chest", r"chest[- ](?:deep|level|high)|up to (?:our |my |the )?(?:chest|neck)|neck[- ]deep|छाती तक|सीने तक|नेक तक|nenju vare|നെഞ്ച്"),
    ("waist", r"waist[- ]deep|up to (?:our |my |the )?waist|कमर तक|aravattam|അരയോളം|at the windows?|window level"),
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


# "Water came in" says nothing about how deep it is. A model band quoting only these words is dropped.
_ENTERED_ONLY = re.compile(r"^\W*(?:വെള്ളം\s*)?(?:കയറി|കയറുന്നു|കേറി)\W*$|^\W*(?:water\s+)?(?:entered|came in|is coming in|got in)\W*$|^\W*(?:paani\s+|पानी\s+)?(?:aa gaya|ghus gaya|आ गया|घुस गया)\W*$", re.I)


def _quote_of(request: Any) -> str:
    wd = getattr(request, "water_depth", None)
    if isinstance(wd, dict):
        return str(wd.get("quote") or "")
    return str(getattr(wd, "quote", "") or "")


def fill_depth(request: Any) -> None:
    """Keep a quoted model band; otherwise read the report words. Unknown stays unknown."""
    if band_of(request) != "unknown":
        quote = _quote_of(request).strip()
        if quote and _ENTERED_ONLY.search(quote) and not depth_from_text(quote):
            request.water_depth = {"band": "unknown", "quote": None, "source": "rules"}
        else:
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
