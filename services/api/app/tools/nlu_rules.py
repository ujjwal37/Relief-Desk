"""Deterministic place and vulnerability repairs for Hindi and Hinglish reports.

The model fallback sometimes keeps the whole sentence as the place and misses
spellings such as "bachcha". These rules run after parsing so a cached model
answer cannot drop the ward or a child.
"""
from __future__ import annotations

import re
from typing import Dict, Optional

_CHILD = (
    "bachcha", "baccha", "bachha", "bachhe", "bacche", "bache", "bachcha",
    "child", "children", "baby", "kid", "kids", "बच्चा", "बच्चे", "बच्ची", "बालक",
)
_ELDERLY = (
    "bujurg", "buzurg", "budha", "budhiya", "elderly", "senior", "dada", "dadi",
    "बुजुर्ग", "बूढ़", "बुजुर्ग", "दादी", "दादा",
)
_PREGNANT = ("pregnant", "pregnancy", "garbhvati", "गर्भवती", "प्रेग्नेंट")
_DISABLED = ("disabled", "handicap", "wheelchair", "divyang", "दिव्यांग", "अपंग")
_STOP = {
    "par", "pe", "per", "mein", "me", "mai", "hai", "hain", "ke", "ki", "aur",
    "bhi", "se", "ko", "ka", "par",
}


def _has_any(text: str, words: tuple) -> bool:
    lower = text.lower()
    for word in words:
        if re.search(r"[\u0900-\u097F]", word):
            if word in text:
                return True
            continue
        if re.search(rf"(?<![a-z]){re.escape(word)}(?![a-z])", lower):
            return True
    return False


def vulnerable_flags(text: str) -> Dict[str, bool]:
    return {
        "child": _has_any(text, _CHILD),
        "elderly": _has_any(text, _ELDERLY),
        "pregnant": _has_any(text, _PREGNANT),
        "disabled": _has_any(text, _DISABLED),
    }


def extract_place(text: str) -> Optional[str]:
    """Pull a ward plus road, or a trailing landmark, out of a spoken report."""
    if not text:
        return None
    ward = re.search(
        r"((?:ward|वार्ड)\s*\d+\b(?:\s+[\w\u0900-\u097F.]{2,}){0,4})",
        text,
        flags=re.IGNORECASE,
    )
    if ward:
        tokens = ward.group(1).split()
        kept = []
        for token in tokens:
            if kept and token.lower().strip(".,") in _STOP:
                break
            kept.append(token.strip(".,"))
        place = " ".join(kept).strip(" ,.")
        if place:
            return place

    landmark = re.search(
        r"(?:near|at|paas|के पास|पास)\s+([A-Za-z0-9\u0900-\u097F][^,.]{2,48})",
        text,
        flags=re.IGNORECASE,
    )
    if landmark:
        return landmark.group(1).strip(" ,.")
    return None


def people_count(text: str) -> Optional[int]:
    match = re.search(r"(\d+)\s*(?:log|लोग|people|persons|insaan)\b", text, flags=re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def hazard_name(text: str) -> Optional[str]:
    lower = text.lower()
    if any(w in lower for w in ("paani", "pani", "पानी", "water rising", "water", "बाढ़", "flood")):
        if any(w in lower for w in ("bhar", "badh", "rising", "भर", "बढ़", "flood", "बाढ़", "फंस")):
            return "water_rising"
        if "paani" in lower or "pani" in lower or "पानी" in text:
            return "water_rising"
    if any(w in lower for w in ("stranded", "trapped", "फंसे", "फंस")):
        return "stranded"
    return None
