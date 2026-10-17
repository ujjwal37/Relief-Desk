"""Deterministic place and vulnerability repairs for Hindi and Hinglish reports.

The model fallback sometimes keeps the whole sentence as the place and misses
spellings such as "bachcha". These rules run after parsing so a cached model
answer cannot drop the ward or a child.
"""
from __future__ import annotations

import re
from typing import Dict, Optional

_CHILD = (
    "bachcha", "baccha", "bachha", "bachhe", "bacche", "bache", "bachcha", "infant", "infants", "newborn",
    "child", "children", "baby", "babies", "kid", "kids", "बच्चा", "बच्चे", "बच्ची", "बालक", "नवजात", "शिशु",
    "കുട്ടി", "കുട്ടികൾ", "കുഞ്ഞ്", "കുഞ്ഞുങ്ങൾ", "മക്കൾ",
)
_ELDERLY = (
    "bujurg", "buzurg", "budha", "budhiya", "elderly", "senior", "dada", "dadi",
    "बुजुर्ग", "बूढ़", "बुढ़", "दादी", "दादा", "नानी", "नाना", "old man", "old woman", "aged",
    "വൃദ്ധൻ", "വൃദ്ധർ", "പ്രായമായവർ", "മുത്തശ്ശി", "മുത്തശ്ശൻ", "അമ്മൂമ്മ", "അപ്പൂപ്പൻ",
)
_PREGNANT = ("pregnant", "pregnancy", "garbhvati", "pet se", "गर्भवती", "गर्भ", "प्रेग्नेंट", "पेट से", "ഗർഭിണി", "ഗർഭം")
_DISABLED = ("disabled", "handicap", "wheelchair", "divyang", "दिव्यांग", "अपंग", "വികലാംഗർ", "ഭിന്നശേഷി", "കിടപ്പിലായ")
_MEDICAL = (
    "medical", "oxygen", "insulin", "dialysis", "doctor", "bedridden", "ऑक्सीजन", "दवा", "बीमार", "डायलिसिस",
    "രോഗി", "ഓക്സിജൻ", "മരുന്ന്", "ഡയാലിസിസ്", "ആശുപത്രി", "ശ്വാസം",
)
_STOP = {
    "par", "pe", "per", "mein", "me", "mai", "hai", "hain", "ke", "ki", "aur",
    "bhi", "se", "ko", "ka", "par",
    "ൽ", "യിൽ", "ആണ്", "ഉണ്ട്", "ഉം", "കൂടെ",
}


def _has_any(text: str, words: tuple) -> bool:
    lower = text.lower()
    for word in words:
        if re.search(r"[\u0900-\u097F\u0D00-\u0D7F]", word):
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


_DEVA_DIGITS = str.maketrans("०१२३४५६७८९൦൧൨൩൪൫൬൭൮൯", "01234567890123456789")

_HI_NUMBER_WORDS = {
    "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5,
    "छह": 6, "छः": 6, "सात": 7, "आठ": 8, "नौ": 9, "दस": 10,
    "ग्यारह": 11, "बारह": 12, "तेरह": 13, "चौदह": 14, "पंद्रह": 15, "सोलह": 16,
    "सत्रह": 17, "अठारह": 18, "उन्नीस": 19, "बीस": 20,
}
_ML_NUMBER_WORDS = {
    "ഒന്ന്": 1, "രണ്ട്": 2, "മൂന്ന്": 3, "നാല്": 4, "അഞ്ച്": 5,
    "ആറ്": 6, "ഏഴ്": 7, "എട്ട്": 8, "ഒൻപത്": 9, "പത്ത്": 10,
    "പതിനൊന്ന്": 11, "പന്ത്രണ്ട്": 12, "ഇരുപത്": 20,
}
# Hinglish number words before "log" ("teen log").
_HINGLISH_NUMBER_WORDS = {
    "ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "chhe": 6, "chhah": 6,
    "saat": 7, "aath": 8, "nau": 9, "das": 10, "gyarah": 11, "barah": 12, "bees": 20,
}


def _ascii_digits(text: str) -> str:
    return text.translate(_DEVA_DIGITS)


def extract_place(text: str) -> Optional[str]:
    """Pull a ward plus road, or a trailing landmark, out of a spoken report."""
    if not text:
        return None
    text = _ascii_digits(text)
    ward = re.search(
        r"((?:ward|वार्ड|വാർഡ്)\s*\d+\b(?:\s+[\w\u0900-\u097F\u0D00-\u0D7F.]{2,}){0,4})",
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
        r"([A-Za-z0-9\u0D00-\u0D7F][\w\u0D00-\u0D7F]{2,}(?:\s+[A-Za-z0-9\u0D00-\u0D7F][\w\u0D00-\u0D7F]{2,}){0,3}\s+(?:road|rd|lane|street|nagar|church|റോഡ്|പാലം|ജെട്ടി|ബോട്ട് ജെട്ടി))",
        text,
        flags=re.IGNORECASE,
    )
    if street:
        return street.group(1).strip(" ,.")

    landmark = re.search(
        r"(?:(?:^|(?<=\s))(?:near|at|paas)|के पास|पास|അടുത്ത്|സമീപം)\s+([A-Za-z0-9\u0900-\u097F\u0D00-\u0D7F][^,.]{2,48})",
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
    r"|people|persons?|adults?|women|woman|men|man|girls?|boys?|patients?|students?|family\s+members"
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


_INJECTION = re.compile(
    r"\b(ignore|disregard|forget|override)\b[^.!?\n]*\b(instruction|instructions|prompt|rules|above|previous)\b"
    r"|\b(mark|set|rate|classify)\s+(this|it|the case|urgency|priority)\b[^.!?\n]*\b(as|to)\b"
    r"|\b(system|assistant)\s*:",
    re.IGNORECASE,
)


def strip_injection(text: str) -> str:
    """Drop sentences that try to instruct the system. Their numbers are never facts about people."""
    if not text:
        return text
    parts = re.split(r"(?<=[.!?\n])\s+", text)
    return " ".join(p for p in parts if not _INJECTION.search(p))


def people_bounds(text: str) -> Optional[tuple]:
    """(low, high, label) for '4 people' or '2-3 people'. The label keeps the words the citizen used."""
    if not text:
        return None
    text = strip_injection(text)
    normalized = _ascii_digits(text)
    ranged = re.search(
        r"(\d+)\s*(?:-|–|—|\bto\b)\s*(\d+)\s*(?:log|लोग|people|persons|insaan|व्यक्ति|ആളുകൾ|പേർ|പേര്)(?:ों|ें)?(?!\w)",
        normalized,
        flags=re.IGNORECASE,
    )
    if ranged:
        low, high = sorted((int(ranged.group(1)), int(ranged.group(2))))
        return low, high, f"{low}-{high}"
    count = _people_count_single(normalized)
    if count is None:
        return None
    return count, count, str(count)


def people_count(text: str) -> Optional[int]:
    """People needed. A range uses the upper bound, so '2-3 people' counts as 3."""
    bounds = people_bounds(text)
    return None if bounds is None else bounds[1]


def span_upper(span: str) -> int:
    numbers = [int(part) for part in re.findall(r"\d+", span or "")]
    return max(numbers) if numbers else 0


def counts_note(spans: list) -> Optional[str]:
    """'Counts differ: 2-3 vs 4-5' when the reports do not name the same number."""
    ordered = []
    for span in spans:
        if span and span not in ordered:
            ordered.append(span)
    if len(ordered) < 2:
        return None
    return "Counts differ: " + " vs ".join(ordered)


def _people_count_single(normalized: str) -> Optional[int]:
    if not normalized:
        return None
    match = re.search(
        r"(\d+)\s*(?:log|लोग|people|persons|insaan|व्यक्ति|ആളുകൾ|പേർ|പേര്|പേരുകൾ)(?:ों|ें)?(?!\w)",
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
    spoken = "|".join(sorted(_HI_NUMBER_WORDS, key=len, reverse=True))
    hindi = re.search(
        rf"({spoken})\s*(?:लोग|व्यक्ति)(?:ों|ें)?(?!\w)",
        normalized,
    )
    if hindi:
        return _HI_NUMBER_WORDS[hindi.group(1)]
    ml_spoken = "|".join(sorted(_ML_NUMBER_WORDS, key=len, reverse=True))
    ml_match = re.search(
        rf"({ml_spoken})\s*(?:ആളുകൾ|പേർ|പേര്|കുട്ടികൾ)(?!\w)",
        normalized,
    )
    if ml_match:
        return _ML_NUMBER_WORDS[ml_match.group(1)]
    latin = "|".join(sorted(_HINGLISH_NUMBER_WORDS, key=len, reverse=True))
    hinglish = re.search(rf"(?<![a-z])({latin})\s+(?:log|logon|logo|insaan|bande)(?![a-z])", normalized, flags=re.IGNORECASE)
    if hinglish:
        return _HINGLISH_NUMBER_WORDS[hinglish.group(1).lower()]
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

    animal = has_latin("dog", "dogs", "kutta", "kutte", "snake", "saanp", "rabies") or has_phrase("कुत्ता", "कुत्ते", "साँप", "सांप", "പട്ടി", "പാമ്പ്")
    if animal and (has_latin("bite", "bit", "bitten", "attack", "attacked", "kaat", "kata", "kaata", "rabies") or has_phrase("काट", "കടിയേറ്റു")):
        return "animal_attack"
    # Medical before food: "needs oxygen, also no khana" is a medical case (life threat first).
    if has_latin("bimar", "bimaar", "dawa", "dawai", "oxygen", "insulin", "dialysis", "doctor", "medicine", "medical",
                 "bleeding", "unconscious", "ambulance", "unresponsive", "fainted") or has_phrase("not breathing", "stopped breathing", "no pulse") or has_phrase(
        "बीमार", "दवा", "ऑक्सीजन", "इंसुलिन", "डॉक्टर", "दवाइ", "डायलिसिस", "can't breathe", "cannot breathe", "साँस",
        "രോഗി", "ഓക്സിജൻ", "മരുന്ന്", "ആശുപത്രി", "ശ്വാസം", "ഡയാലിസിസ്"
    ):
        return "medical"
    if has_latin("ration", "bhook", "bhookh", "khana", "packets") or has_phrase(
        "राशन", "भूख", "खाना", "पीने का पानी", "drinking water", "पैकेट",
        "ഭക്ഷണം", "ഭക്ഷണപ്പൊതി", "കഴിക്കാൻ", "വിശപ്പ്"
    ):
        return "food"
    if has_latin("bachao", "rescue", "stranded", "fanse", "rooftop", "trapped", "marooned", "stuck") or has_phrase("on the roof", "on roof", "chest deep", "chest-deep", "neck deep") or has_phrase(
        "chat par", "chhat par", "छत", "फंसे", "फँसे", "फंस", "fas gaye",
        "boat bhejo", "boat needed", "rescue boat", "send a boat", "boat chahiye",
        "नाव", "बचाओ", "बचाव",
        "രക്ഷിക്കൂ", "രക്ഷാപ്രവർത്തനം", "വഞ്ചി", "ബോട്ട്", "വെള്ളം കയറി", "മുങ്ങി", "മേൽക്കൂര"
    ):
        return "rescue"
    if has_latin("beghar", "tarpaulin") or has_phrase(
        "जगह चाहिए", "jagah chahiye", "घर डूब", "ghar doob", "roof collapsed",
        "emergency shelter", "need shelter", "temporary shelter", "आश्रय", "बेघर",
        "വീട് മുങ്ങി", "താമസിക്കാൻ സ്ഥലം", "അഭയം"
    ):
        return "shelter"
    if not has_latin("help", "need", "needs", "bachao", "madad", "please", "entering", "inside") and has_phrase("waterlogging", "traffic stopped", "road is blocked", "road blocked", "रास्ता बंद", "റോഡ് തടസ്സപ്പെട്ടു"):
        return "info"
    return None


_RECEDED = ("drained", "receded", "water gone", "water has gone", "dry now", "utar gaya", "utar gaya hai", "उतर गया", "सूख")


def hazard_name(text: str) -> Optional[str]:
    lower = text.lower()
    if any(w in lower or w in text for w in _RECEDED):
        return None
    if any(w in lower or w in text for w in ("paani", "pani", "पानी", "water rising", "water", "बाढ़", "flood", "vellam", "വെള്ളം")):
        if any(w in lower or w in text for w in ("bhar", "badh", "rising", "भर", "बढ़", "flood", "बाढ़", "फंस",
                                              "koodunnu", "kooduka", "kerunnu", "keruka", "uyarunnu", "pongunnu",
                                              "കൂടുന്നു", "കയറുന്നു", "ഉയരുന്നു", "പൊങ്ങുന്നു")):
            return "water_rising"
        if "paani" in lower or "pani" in lower or "पानी" in text or "vellam" in lower or "വെള്ളം" in text:
            return "water_rising"
    if any(w in lower for w in ("stranded", "trapped", "फंसे", "फंस", "chhat", "chat par", "boat", "kudungi", "kudunghi", "കുടുങ്ങി")):
        return "stranded"
    return None
