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
    "குழந்தை", "குழந்தைகள்", "சிறுவன்", "சிறுமி", "குழந்தைக்கு",
)
_ELDERLY = (
    "bujurg", "buzurg", "budha", "budhiya", "elderly", "senior", "dada", "dadi",
    "बुजुर्ग", "बूढ़", "बुजुर्ग", "दादी", "दादा",
    "முதியவர்", "முதியவரு", "முதிய", "வயதான", "பாட்டி", "தாத்தா", "வயோதிகர்",
)
_PREGNANT = ("pregnant", "pregnancy", "garbhvati", "गर्भवती", "प्रेग्नेंट", "கர்ப்பிணி")
_DISABLED = ("disabled", "handicap", "wheelchair", "divyang", "दिव्यांग", "अपंग", "மாற்றுத்திறன்")
_MEDICAL = (
    "medical", "oxygen", "insulin", "doctor", "hospital", "ऑक्सीजन", "दवा", "बीमार",
    "ஆக்சிஜன்", "மருத்துவம்", "மருத்துவர்", "நோயாளி", "மருந்து", "ஆஸ்துமா",
)
_TA_DIGITS = str.maketrans("௦௧௨௩௪௫௬௭௮௯", "0123456789")
_TA_NUMBER_WORDS = (
    ("பத்து", 10), ("ஒன்பது", 9), ("எட்டு", 8), ("ஏழு", 7), ("ஆறு", 6),
    ("ஐந்து", 5), ("நான்கு", 4), ("மூன்று", 3), ("இரண்டு", 2), ("ஒன்று", 1), ("ஒரு", 1),
)
_STOP = {
    "par", "pe", "per", "mein", "me", "mai", "hai", "hain", "ke", "ki", "aur",
    "bhi", "se", "ko", "ka", "par",
}


def _has_any(text: str, words: tuple) -> bool:
    lower = text.lower()
    for word in words:
        if re.search(r"[\u0900-\u097F\u0B80-\u0BFF]", word):
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
        "medical_need": _has_any(text, _MEDICAL),
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

    street = re.search(
        r"([A-Za-z0-9][\w]{2,}(?:\s+[A-Za-z][\w]{2,}){0,3}\s+(?:road|rd|lane|street|nagar|church))",
        text,
        flags=re.IGNORECASE,
    )
    if street:
        return street.group(1).strip(" ,.")

    landmark = re.search(
        r"(?:(?:^|(?<=\s))(?:near|at|paas)|के पास|पास)\s+([A-Za-z0-9\u0900-\u097F][^,.]{2,48})",
        text,
        flags=re.IGNORECASE,
    )
    if landmark:
        return landmark.group(1).strip(" ,.")
    return None


_EN_NUMBER_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twelve": 12,
}
_EN_GROUP_NOUNS = (
    r"elderly|old\s+(?:people|persons|men|women)|seniors?|child(?:ren)?|kids?|babies|baby|infants?"
    r"|people|persons|adults?|women|woman|men|man|girls?|boys?|patients?|students?|family\s+members"
)


def _group_people_count(text: str) -> Optional[int]:
    """Add up groups such as '2 elderly and a child' (3). None when no group is named."""
    total = 0
    found = False
    pattern = rf"(?<![\w])(\d+|{'|'.join(_EN_NUMBER_WORDS)})\s+(?:{_EN_GROUP_NOUNS})(?!\w)"
    for match in re.finditer(pattern, text, flags=re.IGNORECASE):
        token = match.group(1).lower()
        total += int(token) if token.isdigit() else _EN_NUMBER_WORDS[token]
        found = True
    return total if found and total > 0 else None


def people_count(text: str) -> Optional[int]:
    if not text:
        return None
    normalized = text.translate(_TA_DIGITS)
    match = re.search(
        r"(\d+)\s*(?:log|लोग|people|persons|insaan|பேர்|பேர்கள்|நபர்|நபர்கள்)(?!\w)",
        normalized,
        flags=re.IGNORECASE,
    )
    if match:
        return int(match.group(1))
    family = re.search(
        rf"(?:family|group)\s+of\s+(\d+|{'|'.join(_EN_NUMBER_WORDS)})(?!\w)|(\d+)[-\s]member\s+family",
        normalized,
        flags=re.IGNORECASE,
    )
    if family:
        token = (family.group(1) or family.group(2)).lower()
        return int(token) if token.isdigit() else _EN_NUMBER_WORDS[token]
    grouped = _group_people_count(normalized)
    if grouped:
        return grouped
    for word, count in _TA_NUMBER_WORDS:
        if re.search(rf"{word}\s*(?:பேர்|பேர்கள்|நபர்|நபர்கள்)", text):
            return count
    return None


def infer_incident_type(text: str) -> Optional[str]:
    """Read the kind of help from the words, not from a place name such as 'shelter' or 'hospital'.

    Returns None when the text has no strong cue, so a model answer can stand.
    """
    if not text:
        return None
    lower = text.lower()

    def has_latin(*words: str) -> bool:
        return any(re.search(rf"(?<![a-z]){re.escape(word)}(?![a-z])", lower) for word in words)

    def has_phrase(*phrases: str) -> bool:
        return any(phrase in text or phrase in lower for phrase in phrases)

    if has_latin("dog", "kutta", "kutte", "rabies", "kaat") or has_phrase("काट", "कुत्ता"):
        return "animal_attack"
    if has_latin("ration", "bhook", "bhookh", "khana", "packets") or has_phrase(
        "राशन", "भूख", "खाना", "पीने का पानी", "drinking water", "पैकेट"
    ):
        return "food"
    if has_latin("bimar", "bimaar", "dawa", "dawai", "oxygen", "insulin", "doctor", "medicine", "medical") or has_phrase(
        "बीमार", "दवा", "ऑक्सीजन", "इंसुलिन", "डॉक्टर", "दवाइ"
    ):
        return "medical"
    if has_latin("bachao", "rescue", "stranded", "fanse", "rooftop") or has_phrase(
        "chat par", "chhat par", "छत", "फंसे", "फंस", "fas gaye",
        "boat bhejo", "boat needed", "rescue boat", "send a boat", "boat chahiye",
    ):
        return "rescue"
    if has_latin("beghar", "tarpaulin") or has_phrase(
        "जगह चाहिए", "jagah chahiye", "घर डूब", "ghar doob", "roof collapsed",
        "emergency shelter", "need shelter", "temporary shelter", "आश्रय", "बेघर",
    ):
        return "shelter"
    if has_phrase("waterlogging", "traffic stopped", "road is blocked", "road blocked", "रास्ता बंद"):
        return "info"
    return None


def hazard_name(text: str) -> Optional[str]:
    lower = text.lower()
    if any(w in lower for w in ("paani", "pani", "पानी", "water rising", "water", "बाढ़", "flood")):
        if any(w in lower for w in ("bhar", "badh", "rising", "भर", "बढ़", "flood", "बाढ़", "फंस")):
            return "water_rising"
        if "paani" in lower or "pani" in lower or "पानी" in text:
            return "water_rising"
    if any(w in lower for w in ("stranded", "trapped", "फंसे", "फंस", "chhat", "chat par", "boat")):
        return "stranded"
    return None
