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

# URL and scam tokens that must never become a place. "bit.ly" used to parse as "bit".
_JUNK_PLACES = {"bit", "bit.ly", "www", "http", "https", "otp", "ly", "com", "html", "no", "yes", "ok", "okay"}

# Kuttanad panchayats drawn on the offline map (apps/web kuttanad-base) that are not all gazetteer wards.
_KUTTANAD_PLACES = ("Pulincunnu", "Kavalam")

_NEGATION = re.compile(
    r"(?<![a-z])(?:nobody|no[\s-]*one|none|not|never|nahi|nahin)(?![a-z])|n['’]t|"
    r"नहीं|नही|कोई नहीं|कोई नही|"
    r"ഇല്ല|അല്ല|ആരുമില്ല|ആരും",
    re.IGNORECASE,
)


def span_negated(text: str, start: int, end: int) -> bool:
    """True when a negation word sits next to the cue (before or just after it)."""
    window = text[max(0, start - 48): min(len(text), end + 24)]
    return _NEGATION.search(window) is not None


def cue_negated(text: str, cue: str) -> bool:
    """True only when every mention of the cue is negated. One positive mention wins."""
    if not text or not cue:
        return False
    lowered = text.lower()
    needle = cue.lower()
    start = 0
    found = False
    while True:
        idx = lowered.find(needle, start)
        if idx < 0:
            break
        found = True
        if not span_negated(text, idx, idx + len(needle)):
            return False
        start = idx + len(needle)
    return found


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


def place_is_usable(place: Optional[str]) -> bool:
    """Reject URL crumbs and yes/no replies. 'bit' from bit.ly is not a village."""
    if not place or not str(place).strip():
        return False
    token = str(place).strip().strip(".,;:").lower()
    if token in _JUNK_PLACES:
        return False
    if re.search(r"https?://|bit\.ly|\bwww\.", token, flags=re.IGNORECASE):
        return False
    return True


def known_place(text: str) -> Optional[str]:
    """Longest gazetteer ward, landmark, or Kuttanad panchayat named in the text."""
    if not text:
        return None
    from app.tools.gazetteer import gazetteer

    names: list[str] = []
    for ward in gazetteer.wards.values():
        if ward.get("name_en"):
            names.append(str(ward["name_en"]))
    for landmark in gazetteer.landmarks:
        if landmark.get("name"):
            names.append(str(landmark["name"]))
        for alias in landmark.get("aliases_en") or []:
            if alias and len(str(alias)) >= 4:
                names.append(str(alias))
    names.extend(_KUTTANAD_PLACES)

    best: Optional[str] = None
    best_len = 0
    best_at = 10**9
    for name in names:
        if len(name) < 4:
            continue
        if re.search(r"[A-Za-z]", name):
            match = re.search(rf"(?<![A-Za-z]){re.escape(name)}(?![A-Za-z])", text, flags=re.IGNORECASE)
            if not match:
                continue
            at = match.start()
            canonical = name
        else:
            at = text.find(name)
            if at < 0:
                continue
            canonical = name
        if len(name) > best_len or (len(name) == best_len and at < best_at):
            best = canonical
            best_len = len(name)
            best_at = at
    return best


def _place_is_weak(place: str) -> bool:
    if not place_is_usable(place):
        return True
    stripped = place.strip()
    if re.match(r"^\d", stripped):
        return True
    return stripped.count(" ") > 8 or len(stripped) > 60


def extract_place(text: str) -> Optional[str]:
    """Pull a ward plus road, a landmark, or a known Kuttanad panchayat."""
    if not text:
        return None
    original = text
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
    ruled = landmark.group(1).strip(" ,.") if landmark else None
    known = known_place(original)
    if known and (not ruled or known.lower() not in ruled.lower()):
        if not ruled or _place_is_weak(ruled):
            return known
    if ruled and place_is_usable(ruled):
        return ruled
    return known if place_is_usable(known) else None


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
        r"(\d+)\s*(?:-|–|—|\bto\b)\s*(\d+)\s*(?:log|लोग|people|persons|insaan|व्यक्ति|ആളുകൾ|പേർ|പേര്|per)(?:ों|ें)?(?!\w)",
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


_BARE_NUMBER_WORDS = {
    **{key: value for key, value in _EN_NUMBER_WORDS.items() if key not in ("a", "an")},
    **_HINGLISH_NUMBER_WORDS,
    **_HI_NUMBER_WORDS,
    **_ML_NUMBER_WORDS,
}

_UNKNOWN_PEOPLE = re.compile(
    r"(not sure|don'?t know|do not know|unknown|not stated|not known|"
    r"pata nahi|nahi pata|nahin pata|mujhe nahi pata|malum nahi|"
    r"पता नहीं|मुझे पता नहीं|नहीं पता|"
    r"ഉറപ്പില്ല|അറിയില്ല|എനിക്ക് ഉറപ്പില്ല)",
    re.IGNORECASE,
)


def _words_for_count(count: int) -> tuple:
    words = [key for key, value in _BARE_NUMBER_WORDS.items() if value == count]
    return tuple(words)


def count_is_stated(text: str, count: Optional[int]) -> bool:
    """True when the report itself names this headcount. A missing count is not 0 or 1."""
    if count is None or not text:
        return False
    if people_count(text) == count:
        return True
    digits = _ascii_digits(text)
    if re.search(rf"(?<!\d){int(count)}(?!\d)", digits):
        return True
    lowered = text.lower()
    return any(word in lowered or word in text for word in _words_for_count(int(count)))


def parse_people_reply(text: str) -> tuple:
    """A typed chat answer: ('count', n), ('unknown', None), or ('absent', None).

    Bare numbers and number words count in English, Hindi, Hinglish, and Malayalam.
    'I am not sure' stays unknown. It is never stored as 0 or 1.
    """
    raw = (text or "").strip()
    if not raw:
        return "absent", None
    if raw in {"?", "??"}:
        return "unknown", None
    counted = people_count(raw)
    digits = _ascii_digits(raw).strip()
    bare = re.fullmatch(r"(\d+)", digits)
    bare_n = int(bare.group(1)) if bare and 1 <= int(bare.group(1)) <= 500 else None
    word_n = _BARE_NUMBER_WORDS.get(raw.strip(" .।")) 
    if word_n is None:
        word_n = _BARE_NUMBER_WORDS.get(raw.lower().strip(" .।"))
    if _UNKNOWN_PEOPLE.search(raw) and counted is None and bare_n is None and word_n is None:
        return "unknown", None
    if bare_n is not None and len(raw) <= 8:
        return "count", bare_n
    if word_n is not None and len(raw.split()) <= 2:
        return "count", word_n
    if counted is not None and counted > 0:
        return "count", counted
    return "absent", None


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
        r"(\d+)\s*(?:log|लोग|people|persons|insaan|व्यक्ति|ആളുകൾ|പേർ|പേര്|പേരുകൾ|per)(?:ों|ें)?(?!\w)",
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
    # "bit" in "bit.ly" is a link, not a bite.
    bit_word = re.search(r"(?<![a-z])bit(?![a-z.])", lower) is not None and "bit.ly" not in lower
    if animal and (has_latin("bite", "bitten", "attack", "attacked", "kaat", "kata", "kaata", "rabies") or bit_word or has_phrase("काट", "കടിയേറ്റു")):
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
    rescue_words = ("bachao", "rescue", "stranded", "fanse", "rooftop", "trapped", "marooned", "stuck")
    rescue_phrases = (
        "on the roof", "on roof", "chest deep", "chest-deep", "neck deep",
        "chat par", "chhat par", "fas gaye",
        "boat bhejo", "boat needed", "rescue boat", "send a boat", "boat chahiye",
        "water rising", "water is rising", "paani badh", "pani badh",
        "vellam koodunnu", "vellam koodunu", "vellam uyaranu", "vellam uyarunnu",
        "छत", "फंसे", "फँसे", "फंस", "नाव", "बचाओ", "बचाव",
        "രക്ഷിക്കൂ", "രക്ഷാപ്രവർത്തനം", "വഞ്ചി", "ബോട്ട്", "വെള്ളം കയറി", "മുങ്ങി", "മേൽക്കൂര",
        "വെള്ളം കൂടുന്നു", "വെള്ളം ഉയരുന്നു",
    )
    rescue_hit = False
    rescue_negated = False
    for word in rescue_words:
        if re.search(rf"(?<![a-z]){re.escape(word)}(?![a-z])", lower):
            if cue_negated(text, word):
                rescue_negated = True
            else:
                rescue_hit = True
    for phrase in rescue_phrases:
        if phrase in text or phrase in lower:
            if cue_negated(text, phrase):
                rescue_negated = True
            else:
                rescue_hit = True
    if rescue_hit:
        return "rescue"
    if has_latin("beghar", "tarpaulin") or has_phrase(
        "जगह चाहिए", "jagah chahiye", "घर डूब", "ghar doob", "roof collapsed",
        "emergency shelter", "need shelter", "temporary shelter", "आश्रय", "बेघर",
        "വീട് മുങ്ങി", "താമസിക്കാൻ സ്ഥലം", "അഭയം"
    ):
        return "shelter"
    if not has_latin("help", "need", "needs", "bachao", "madad", "please", "entering", "inside") and has_phrase("waterlogging", "traffic stopped", "road is blocked", "road blocked", "रास्ता बंद", "റോഡ് തടസ്സപ്പെട്ടു"):
        return "info"
    # "Nobody is stranded" is a status update, not a rescue request.
    if rescue_negated:
        return "info"
    return None


_RECEDED = ("drained", "receded", "water gone", "water has gone", "dry now", "utar gaya", "utar gaya hai", "उतर गया", "सूख")


_RISING_CUES = (
    "rising", "koodunnu", "koodunu", "uyaranu", "uyarunnu", "badh", "bhar",
    "बढ़", "भर", "കൂടുന്നു", "ഉയരുന്നു",
)
_WATER_WORDS = ("paani", "pani", "पानी", "water", "बाढ़", "flood", "vellam", "വെള്ളം")


def _rising_is_positive(text: str) -> bool:
    """True when a rising-water cue is present and not inside a negation."""
    hits = [cue for cue in _RISING_CUES if cue in text.lower() or cue in text]
    if not hits:
        return False
    return any(not cue_negated(text, cue) for cue in hits)


def hazard_name(text: str) -> Optional[str]:
    if not text:
        return None
    lower = text.lower()
    if any(w in lower or w in text for w in _RECEDED):
        return None
    has_water = any(w in lower or w in text for w in _WATER_WORDS)
    if has_water and _rising_is_positive(text):
        return "water_rising"
    if any(w in lower or w in text for w in ("paani", "pani", "पानी", "vellam", "വെള്ളം")) and not any(
        cue_negated(text, word) for word in ("paani", "pani", "vellam", "വെള്ളം") if word in lower or word in text
    ):
        return "water_rising"
    for cue in ("stranded", "trapped", "फंसे", "फंस", "chhat", "chat par", "boat"):
        if (cue in lower or cue in text) and not cue_negated(text, cue):
            return "stranded"
    return None


def water_stated(text: str) -> Optional[str]:
    """What the report already said about the water, or None when it did not say.

    'vellam koodunnu' is rising water, so the chat must not ask 'is the water rising?'.
    """
    if not text:
        return None
    if hazard_name(text) == "water_rising":
        return "rising"
    lower = text.lower()
    depths = (
        ("roof", ("on the roof", "on roof", "rooftop", "chat par", "chhat par", "മേൽക്കൂര", "छत")),
        ("chest", ("chest deep", "chest-deep", "chest deep")),
        ("waist", ("waist deep", "waist-deep", "kamar tak")),
        ("knee", ("knee deep", "knee-deep", "ghutne tak")),
        ("ankle", ("ankle deep", "ankle-deep")),
    )
    for band, cues in depths:
        for cue in cues:
            if (cue in lower or cue in text) and not cue_negated(text, cue):
                return band
    if re.search(r"(?<![a-z])(?:not rising|water is not|paani nahi badh|vellam illa)(?![a-z])", lower) or "വെള്ളം ഇല്ല" in text:
        return "none"
    return None


def need_from_reply(text: str) -> Optional[str]:
    """A short answer to 'what do you need?'."""
    kind = infer_incident_type(text)
    if kind:
        return kind
    lowered = (text or "").lower()
    table = (
        ("rescue", ("rescue", "boat", "bachao", "बचाव", "രക്ഷ")),
        ("medical", ("medical", "doctor", "ambulance", "दवाई", "മെഡിക്കൽ")),
        ("food", ("food", "khana", "ration", "खाना", "ഭക്ഷണം")),
        ("shelter", ("shelter", "ashray", "आश्रय", "അഭയം")),
        ("info", ("info", "update", "status")),
    )
    for name, words in table:
        if any(word in lowered or word in (text or "") for word in words):
            return name
    return None


def place_from_answer(text: str) -> Optional[str]:
    """A reply to 'where are you?'. A bare number is a headcount, not a place."""
    raw = (text or "").strip()
    if not raw or not place_is_usable(raw):
        return None
    status, _count = parse_people_reply(raw)
    if status == "count" and len(raw.split()) <= 2:
        return None
    if status == "unknown":
        return None
    known = known_place(raw)
    if known:
        return known
    ruled = extract_place(raw)
    if ruled and place_is_usable(ruled) and not _place_is_weak(ruled):
        return ruled
    if re.fullmatch(r"[\d\s?.!-]+", raw):
        return None
    if len(raw) < 3 or len(raw) > 80:
        return None
    return raw.strip(" .,")


def water_from_answer(text: str) -> Optional[str]:
    stated = water_stated(text)
    if stated:
        return stated
    raw = (text or "").strip()
    lowered = raw.lower()
    if re.fullmatch(r"(yes|haan|han|ha|ji|हाँ|हां|അതെ|rising|badh raha|koodunnu|uyarunnu)", lowered) or raw in {"हाँ", "हां", "അതെ"}:
        return "rising"
    if re.fullmatch(r"(no|nahi|nahin|nope)", lowered) or raw in {"नहीं", "നഹി", "ഇല്ല", "അല്ല"}:
        return "none"
    return None
