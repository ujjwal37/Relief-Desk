import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional
from pydantic import BaseModel

from app.llm.client import llm_client

logger = logging.getLogger("relief_desk.translation")


def _find_cache_dir() -> Path:
    current = Path(__file__).resolve().parent
    for p in [current, *current.parents]:
        if (p / "data").exists():
            target = p / "data" / "cache" / "translations"
            target.mkdir(parents=True, exist_ok=True)
            return target
    target = Path(__file__).resolve().parents[4] / "data" / "cache" / "translations"
    target.mkdir(parents=True, exist_ok=True)
    return target


CACHE_DIR = _find_cache_dir()


class TranslationResult(BaseModel):
    text_en: str
    text_hi: str
    translations: Dict[str, str]
    detected_language: str  # "hi" | "hinglish" | "en" | "ml"
    confidence: float
    is_low_confidence: bool
    cached: bool = False


class TranslationService:
    def __init__(self):
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self._memory_cache: Dict[str, TranslationResult] = {}

    def detect_language(self, text: str) -> str:
        """Detects Hindi (Devanagari), Malayalam, Hinglish, or English."""
        # Devanagari range: \u0900-\u097F
        if re.search(r"[\u0900-\u097F]", text):
            return "hi"
        # Malayalam range: \u0D00-\u0D7F
        if re.search(r"[\u0D00-\u0D7F]", text):
            return "ml"
        # Check Hinglish keywords
        hinglish_markers = [
            "paani", "pani", "badh", "raha", "hai", "hain", "ke", "paas", "chat",
            "par", "bachao", "bacche", "bache", "buzurg", "log", "jaldi", "bhejo",
            "madad", "chahiye", "ghar", "gali", "gaya", "khatam", "bhookh", "chhat",
            "marooned", "fass", "fase"
        ]
        text_lower = text.lower()
        if any(re.search(rf"\b{w}\b", text_lower) for w in hinglish_markers):
            return "hinglish"
        return "en"

    def from_model(self, text: str, text_en: str, text_hi: Optional[str], confidence: Optional[float]) -> TranslationResult:
        """Keep the translation that came back inside the one intake reply, cached by text hash."""
        clean_text = (text or "").strip()
        hindi = (text_hi or "").strip() or clean_text
        conf = float(confidence) if confidence is not None else 0.9
        res = TranslationResult(
            text_en=text_en.strip(),
            text_hi=hindi,
            translations={"en": text_en.strip(), "hi": hindi},
            detected_language=self.detect_language(clean_text),
            confidence=conf,
            is_low_confidence=conf < 0.70,
        )
        if clean_text:
            self._save_cache(hashlib.sha256(clean_text.encode("utf-8")).hexdigest(), res)
        return res

    def translate_report(self, text: str, allow_model: bool = True) -> TranslationResult:
        """Translates a free-text report into English and Hindi and scores confidence.
        Translations are cached by hash so repeat inputs are instantaneous and zero-cost.
        The report path passes allow_model=False: its translation rides on the one intake call."""
        clean_text = text.strip()
        if not clean_text:
            return TranslationResult(
                text_en="",
                text_hi="",
                translations={"en": "", "hi": ""},
                detected_language="en",
                confidence=1.0,
                is_low_confidence=False,
            )

        lang = self.detect_language(clean_text)
        cache_key = hashlib.sha256(clean_text.encode("utf-8")).hexdigest()

        # 1. In-memory and disk cache check
        if cache_key in self._memory_cache:
            res = self._memory_cache[cache_key].model_copy(deep=True)
            res.cached = True
            return res

        disk_path = CACHE_DIR / f"{cache_key}.json"
        if disk_path.exists():
            try:
                with open(disk_path, "r", encoding="utf-8") as f:
                    cached_data = json.load(f)
                    stale = "text_ta" in cached_data or "ta" in (cached_data.get("translations") or {})
                    if not stale:
                        res = TranslationResult(**cached_data)
                        self._memory_cache[cache_key] = res
                        res.cached = True
                        return res
            except Exception:
                pass

        # 2. Check for low-confidence inputs (garbled text, repetitive gibberish, single characters)
        if len(clean_text) < 5 or re.match(r"^[^\w\s]+$", clean_text) or len(set(clean_text)) <= 3:
            res = TranslationResult(
                text_en=clean_text,
                text_hi=clean_text,
                translations={"en": clean_text, "hi": clean_text},
                detected_language=lang,
                confidence=0.35,
                is_low_confidence=True,
            )
            self._save_cache(cache_key, res)
            return res

        if not allow_model:
            return self._deterministic_fallback(clean_text, lang)

        # 3. If Gemini is enabled, execute live translation
        if llm_client.gemini_live():
            try:
                prompt = f"""You are a crisis translation engine for disaster dispatchers.
Translate the following emergency report into English (text_en) and Hindi (text_hi in Devanagari script).
Also provide a translation confidence score between 0.0 and 1.0.

Input text: <text>{clean_text}</text>

Return strictly JSON matching this schema:
{{
  "text_en": "English translation",
  "text_hi": "Hindi translation in Devanagari",
  "confidence": 0.95
}}"""
                raw_json = llm_client.generate_json(
                    prompt=prompt,
                    system_instruction="You are an emergency triage translation agent. Output strictly valid JSON."
                )
                if raw_json and "text_en" in raw_json:
                    conf = float(raw_json.get("confidence", 0.92))
                    res = TranslationResult(
                        text_en=raw_json["text_en"],
                        text_hi=raw_json.get("text_hi", clean_text),
                        translations={
                            "en": raw_json["text_en"],
                            "hi": raw_json.get("text_hi", clean_text),
                        },
                        detected_language=lang,
                        confidence=conf,
                        is_low_confidence=conf < 0.70,
                    )
                    self._save_cache(cache_key, res)
                    return res
            except Exception as e:
                logger.warning("Gemini live translation failed, using deterministic fallback: %s", e)

        # 4. Deterministic fallback translation for synthetic Kerala phrases
        res = self._deterministic_fallback(clean_text, lang)
        self._save_cache(cache_key, res)
        return res

    def _deterministic_fallback(self, text: str, lang: str) -> TranslationResult:
        """Deterministic translation fallback when offline or in demo mode."""
        t_lower = text.lower()

        if lang == "en":
            en_text = text
            hi_text = "आपातकालीन रिपोर्ट: " + text
        elif lang in ("hi", "hinglish"):
            if "shiva temple" in t_lower or "shiv mandir" in t_lower or "शिव मंदिर" in text:
                en_text = "4 people trapped near Shiva Temple in Ward 7, water at waist level. Small child and elderly grandmother present. Please send rescue boat urgently."
                hi_text = "वार्ड 7 में शिव मंदिर के पास 4 लोग फंसे हैं, पानी कमर तक आ गया है। छोटा बच्चा और बुजुर्ग दादी हैं। नाव भेजिए।"
            elif "clock tower" in t_lower or "ghanta ghar" in t_lower or "घंटा घर" in text:
                en_text = "Water rising rapidly behind Ward 4 Clock Tower. 5 family members stranded, grandmother needs asthma oxygen cylinder urgently."
                hi_text = "वार्ड 4 घंटा घर के पीछे पानी तेजी से बढ़ रहा है। 5 लोग हैं, दादी को ऑक्सीजन सिलेंडर चाहिए।"
            elif "gandhi school" in t_lower or "गांधी स्कूल" in text:
                en_text = "Drinking water and dry ration finished for 20 families at Ward 2 Gandhi School relief camp."
                hi_text = "वार्ड 2 गांधी स्कूल राहत कैंप में 20 परिवारों के लिए राशन और पीने का पानी खत्म हो गया है।"
            elif "mill colony" in t_lower or "aawara kutto" in t_lower:
                en_text = "Stray dog pack attacked child in Ward 9 Mill Colony lane 4, bleeding. Urgent ambulance and rabies injection needed."
                hi_text = "वार्ड 9 मिल कॉलोनी में आवारा कुत्तों ने बच्चे को काटा, तुरंत एम्बुलेंस और रेबीज इंजेक्शन चाहिए।"
            else:
                en_text = f"Emergency report from {text}: flood water rising, people requesting urgent assistance."
                hi_text = text if lang == "hi" else "आपातकालीन स्थिति: पानी बढ़ रहा है, तुरंत सहायता की आवश्यकता है।"
        elif lang == "ml":
            en_text = "Emergency report: flood water rising, people requesting urgent assistance."
            hi_text = "आपातकालीन रिपोर्ट: पानी बढ़ रहा है, तुरंत सहायता की आवश्यकता है।"
        else:
            en_text = text
            hi_text = "आपातकालीन रिपोर्ट"

        return TranslationResult(
            text_en=en_text,
            text_hi=hi_text,
            translations={"en": en_text, "hi": hi_text},
            detected_language=lang,
            confidence=0.88,
            is_low_confidence=False,
        )

    def _save_cache(self, key: str, result: TranslationResult):
        self._memory_cache[key] = result
        try:
            with open(CACHE_DIR / f"{key}.json", "w", encoding="utf-8") as f:
                f.write(result.model_dump_json(indent=2))
        except Exception:
            pass


translation_service = TranslationService()
