import re
from typing import Literal, Optional, Tuple

GateOutcome = Literal["greeting", "gibberish", "report"]

# Life-threat words bypass the gate even when the message is short.
_LIFE_THREAT_PATTERN = re.compile(
    r"\b(?:not\s+breath(?:ing)?|can'?t\s+breathe?|breathe?|breathless|breathing|"
    r"oxygen|dialysis|insulin|unconscious|bleeding|severe\s+injury|heart\s+attack|labour|pregnant)\b|"
    r"ശ്വാസം(?:\s*കിട്ടുന്നില്ല|\s*മുട്ടുന്നു)?|ജീവന്\s*ഭീഷണി|"
    r"साँस(?:\s*नहीं|\s*रुकी|\s*फूल)?|ऑक्सीजन|डायलिसिस|इंसुलिन|रक्तस्राव|बेहोश|"
    r"\b(?:swasam|shwasam|jeevan)\b",
    re.IGNORECASE,
)

# Greeting words in English, Hindi/Hinglish, and Malayalam.
_GREETING_WORDS = {
    "hi", "hello", "hey", "ok", "okay", "k", "test", "testing",
    "namaste", "namaskar", "pranam", "radhe", "ram",
    "नमस्ते", "प्रणाम", "हेलो", "हाय", "नमस्कार",
    "ഹായ്", "ഹലോ", "നമസ്കാരം", "നമസ്തേ", "സുഖമാണോ",
}

_GREETING_PHRASES = re.compile(
    r"^(?:hi|hello|hey|ok|okay|k|test|testing|good\s+(?:morning|evening|afternoon)|"
    r"namaste|namaskar|pranam|radhe\s+radhe|ram\s+ram|"
    r"नमस्ते|प्रणाम|हेलो|हाय|नमस्कार|"
    r"ഹായ്|ഹലോ|നമസ്കാരം|നമസ്തേ|സുഖമാണോ)[\s.!,?]*$",
    re.IGNORECASE,
)

# Emergency & crisis indicators across all 4 languages.
_EMERGENCY_WORDS = re.compile(
    r"\b(?:help|rescue|save|trapped|stuck|marooned|flood|flooded|water|rising|boat|vallam|food|ration|shelter|"
    r"urgent|emergency|ambulance|doctor|hospital|clinic|sick|injured|injury|hurt|pain|submerged|submerge|"
    r"roof|rooftop|terrace|wall|house|home|canal|river|road|bridge|jetty|temple|church|school|camp|"
    r"elderly|child|children|baby|infant|kid|pregnant|disabled|handicapped|blind|bedridden|"
    r"family|people|person|persons|log|aalukal|per|peru|aalu|und|undu|kutti|ammachi|ammavan|nadakkan|pattilla|"
    r"sahayam|venam|varanam|vellam|keri|kayari|koodi|ottappettu|veetil|veettil|veedu|mukalil|"
    r"nasa|dam|burst|evacuate|forward|warn|warning|alert)\b|"
    r"(?:मदद|बचाव|फंसे|फंसा|पानी|बाढ़|जलभराव|नाव|खाना|राशन|आश्रय|तुरंत|आपात|एम्बुलेंस|डॉक्टर|अस्पताल|बीमार|चोट|दर्द|"
    r"डूब|छत|घर|दीवार|नहर|नदी|सड़क|रोड|पुल|मंदिर|चर्च|स्कूल|राहत|शिविर|बुजुर्ग|बच्चा|बच्चे|गर्भवती|दिव्यांग|"
    r"लोग|परिवार|सहायता|चाहिए|भेजो|डैम|खाली)|"
    r"(?:സഹായം|രക്ഷ|കുടുങ്ങി|വെള്ളം|പ്രളയം|ഉയരുന്നു|ബോട്ട്|വള്ളം|ഭക്ഷണം|റേഷൻ|അഭയം|അടിയന്തിരം|ആംബുലൻസ്|ഡോക്ടർ|ആശുപത്രി|"
    r"രോഗി|പരുക്ക്|വേദന|മുങ്ങി|മേൽക്കൂര|വീട്|റോഡ്|പാലം|ജെട്ടി|ക്ഷേത്രം|പള്ളി|സ്കൂൾ|ക്യാമ്പ്|പ്രായമായവർ|കുട്ടി|കുട്ടികൾ|"
    r"ഗർഭിണി|ഭിന്നശേഷി|ആളുകൾ|പേർ|വേണം|വരണം|പെട്ടെന്ന്|ഡാം|ഒഴിപ്പിക്കുക)",
    re.IGNORECASE,
)

_KNOWN_PLACES = re.compile(
    r"\b(?:kainakary|champakulam|nedumudi|aluva|varapuzha|kothamangalam|chalakudy|mala|anthikad|meppadi|vythiri|kalpetta|"
    r"kuttanad|pulincunnu|pulinkunnu|kavalam|ramankari|ramankary|mankombu|moncompu|thakazhy|thakazhi|"
    r"edathua|thalavady|muttar|veliyanad|kidangara|neelamperoor|thottappally|"
    r"ward\s*\d+|ward|jetty|ghat|bridge|church|temple|school|st\s+mary)\b|"
    r"(?:काइनकरी|चम्पाकुलाम|नेदुमुडी|आलुवा|वरप्पुषा|कोथमंगलम|चालाकुडी|माला|अंतिक्काड|मेप्पाडी|वित्तूरि|कल्पेट्टा|कुट्टनाड|वार्ड)|"
    r"(?:കൈനകരി|ചമ്പക്കുളം|നെടുമുടി|ആലുവ|വരാപ്പുഴ|കോതമംഗലം|ചാലക്കുടി|മാള|അന്തിക്കാട്|മേപ്പാടി|വൈത്തിരി|കൽപ്പറ്റ|കുട്ടനാട്|വാർഡ്)",
    re.IGNORECASE,
)

_COUNT_PATTERNS = re.compile(
    r"\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|twenty|thirty|forty|fifty)\s*"
    r"(?:people|persons|log|per|aalukal|members|individuals|souls)?\b|"
    r"(?:\d+|एक|दो|तीन|चार|पाँच|छह|सात|आठ|नौ|दस)\s*(?:लोग|व्यक्ति)?|"
    r"(?:\d+|ഒന്ന്|രണ്ട്|മൂന്ന്|നാല്|അഞ്ച്|ആറ്)\s*(?:പേർ|ആളുകൾ)?",
    re.IGNORECASE,
)

_MANGLISH_WORDS_PATTERN = re.compile(
    r"\b(?:vellam|kayari|keri|und|undu|illa|venam|sahayam|veettil|veetil|veedu|aduthu|nadakkan|pattilla|ammachi|kutti|per|peru|aalukal|aalu|vallam|mukalil|ottappettu|varanam|koodi)\b",
    re.IGNORECASE,
)

_RESPONSES = {
    "greeting": {
        "en": "Tell me what's happening and where",
        "hi": "बताएं क्या हो रहा है और आप कहाँ हैं",
        "hinglish": "Bataiye kya ho raha hai aur aap kahan hain",
        "ml": "എന്താണ് സംഭവിക്കുന്നതെന്നും എവിടെയാണെന്നും പറയൂ",
        "manglish": "Enthanu sambhavikkunnath ennum evideyanennum parayoo",
    },
    "gibberish": {
        "en": "I couldn't understand — describe the emergency and place",
        "hi": "मैं समझ नहीं पाया — कृपया आपात स्थिति और स्थान बताएं",
        "hinglish": "Main samajh nahi paya — kripya emergency aur jagah batayein",
        "ml": "എനിക്ക് മനസ്സിലായില്ല — അടിയന്തരാവസ്ഥയും സ്ഥലവും വിവരിക്കുക",
        "manglish": "Manassilayilla — emergency-yum sthalavum parayoo",
    },
}


def is_manglish(text: str) -> bool:
    """True if text has Latin characters and common Manglish words."""
    if not text or re.search(r"[\u0D00-\u0D7F\u0900-\u097F]", text):
        return False
    return bool(_MANGLISH_WORDS_PATTERN.search(text))


def detect_script_lang(text: str, fallback_lang: Optional[str] = "en") -> str:
    """Detect whether input is Malayalam script, Devanagari (Hindi), Manglish, Hinglish, or English."""
    raw = text or ""
    if re.search(r"[\u0D00-\u0D7F]", raw):
        return "ml"
    if re.search(r"[\u0900-\u097F]", raw):
        return "hi"
    if is_manglish(raw) or fallback_lang == "manglish":
        return "manglish"
    if fallback_lang == "hinglish" or fallback_lang == "hi":
        return "hinglish"
    if fallback_lang in ("en", "ml"):
        return fallback_lang
    return "en"


def is_life_threat(text: str) -> bool:
    """True if message cites immediate life threat symptoms (oxygen, breathing, bleeding, etc.)."""
    return bool(_LIFE_THREAT_PATTERN.search(text or ""))


def evaluate_input_gate(
    text: Optional[str],
    lang: Optional[str] = None,
    lang_hint: Optional[str] = None,
    has_photo: bool = False,
    photo_is_emergency: bool = True,
) -> Tuple[GateOutcome, Optional[str]]:
    """Evaluates raw text against greeting and gibberish gates.
    
    Returns:
        (outcome, reply_message)
        where outcome is 'greeting', 'gibberish', or 'report'.
    """
    raw = (text or "").strip()
    chosen_lang = lang or lang_hint
    detected_lang = detect_script_lang(raw, fallback_lang=chosen_lang)

    # 1. Life threat always bypasses the gate, even when message is short.
    if is_life_threat(raw):
        return "report", None

    # 2. Hoax / spam phrases must create a held/flagged case, not gibberish.
    from app.tools.trust import VIRAL_HOAX_PHRASES
    raw_lower = raw.lower()
    if any(phrase in raw_lower for phrase in VIRAL_HOAX_PHRASES):
        return "report", None

    # 3. Blank check (whitespace only -> greeting, unless photo report)
    if not raw:
        if has_photo and photo_is_emergency:
            return "report", None
        reply = _RESPONSES["greeting"].get(detected_lang, _RESPONSES["greeting"]["en"])
        return "greeting", reply

    # 4. Greeting check (specific greeting tokens/phrases)
    clean = re.sub(r"[^\w\s\u0900-\u097F\u0D00-\u0D7F]", "", raw).strip().lower()
    if clean in _GREETING_WORDS or bool(_GREETING_PHRASES.match(raw)):
        # If photo is attached and represents an emergency, photo makes it a report
        if has_photo and photo_is_emergency:
            return "report", None
        reply = _RESPONSES["greeting"].get(detected_lang, _RESPONSES["greeting"]["en"])
        return "greeting", reply

    # 5. Non-empty text with no alphanumeric characters (e.g. "???") is passed as a report
    # so downstream translation pipeline can evaluate and flag low translation confidence.
    if not clean:
        return "report", None

    # 6. Emergency & report cues (cues, known places, counts, or photo with emergency)
    has_emergency = bool(_EMERGENCY_WORDS.search(raw))
    has_place = bool(_KNOWN_PLACES.search(raw))
    has_count = bool(_COUNT_PATTERNS.search(raw))

    if has_emergency or has_place or has_count:
        return "report", None

    if has_photo and photo_is_emergency:
        return "report", None

    # 7. If none of the emergency cues matched: Gibberish or off-topic conversation
    reply = _RESPONSES["gibberish"].get(detected_lang, _RESPONSES["gibberish"]["en"])
    return "gibberish", reply
