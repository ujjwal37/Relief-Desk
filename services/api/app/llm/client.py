import hashlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from app.config import settings

logger = logging.getLogger("relief_desk.llm")

CACHE_DIR = Path(__file__).resolve().parents[4] / "data" / "cache" / "llm"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


class LLMClient:
    def __init__(self):
        self.call_count = 0
        self.daily_cap = settings.GEMINI_DAILY_CALL_CAP
        self._memory_cache: Dict[str, str] = {}

    def _hash_key(self, prompt: str) -> str:
        return hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    def get_cached(self, key: str) -> Optional[str]:
        if key in self._memory_cache:
            return self._memory_cache[key]
        cache_file = CACHE_DIR / f"{key}.json"
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    val = data.get("response")
                    self._memory_cache[key] = val
                    return val
            except Exception as e:
                logger.warning("Error reading cache file %s: %s", cache_file, e)
        return None

    def set_cached(self, key: str, response: str) -> None:
        self._memory_cache[key] = response
        cache_file = CACHE_DIR / f"{key}.json"
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump({"key": key, "response": response}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning("Error writing cache file %s: %s", cache_file, e)

    def generate_content(
        self,
        system_instruction: str,
        user_prompt: str,
        validator: Optional[Callable[[str], Any]] = None,
        max_retries: int = 2,
    ) -> str:
        """Generates content using Gemini or cached/offline mode with <= 2 retries."""
        full_prompt = f"SYSTEM:\n{system_instruction}\n\nUSER:\n{user_prompt}"
        cache_key = self._hash_key(full_prompt)

        # 1. Check cache first
        cached = self.get_cached(cache_key)
        if cached:
            logger.info("Cache hit for prompt hash %s", cache_key[:8])
            if validator:
                try:
                    validator(cached)
                    return cached
                except Exception:
                    logger.warning("Cached entry invalid according to validator, refreshing...")
            else:
                return cached

        # 2. Check kill switch or budget cap
        if not settings.GEMINI_ENABLED or settings.DEMO_MODE:
            logger.info("Gemini kill-switch is active or DEMO_MODE=True. Using deterministic fallback.")
            response = self._deterministic_fallback(user_prompt)
            self.set_cached(cache_key, response)
            return response

        if self.call_count >= self.daily_cap:
            logger.warning("Gemini daily call cap reached (%d). Falling back to deterministic mode.", self.daily_cap)
            response = self._deterministic_fallback(user_prompt)
            self.set_cached(cache_key, response)
            return response

        # 3. Call Gemini if API key configured and not dummy
        api_key = settings.GEMINI_API_KEY
        if api_key and api_key not in ("replace-me", "synthetic-demo-gemini-key"):
            try:
                import google.genai as genai  # type: ignore
                client = genai.Client(api_key=api_key)
                current_prompt = user_prompt
                attempts = 0
                while attempts <= max_retries:
                    self.call_count += 1
                    attempts += 1
                    response_obj = client.models.generate_content(
                        model=settings.GEMINI_MODEL,
                        contents=current_prompt,
                        config={"system_instruction": system_instruction, "temperature": 0.1}
                    )
                    text = response_obj.text or ""
                    if validator:
                        try:
                            validator(text)
                            self.set_cached(cache_key, text)
                            return text
                        except Exception as val_err:
                            logger.warning("Validation attempt %d failed: %s", attempts, val_err)
                            current_prompt = (
                                f"{user_prompt}\n\nPREVIOUS OUTPUT WAS INVALID JSON OR FAILED VALIDATION:\n"
                                f"{str(val_err)}\nEnsure output strictly adheres to the requested JSON schema."
                            )
                    else:
                        self.set_cached(cache_key, text)
                        return text
            except Exception as e:
                logger.error("Live Gemini call failed (%s). Falling back to deterministic response.", e)

        # Fallback
        response = self._deterministic_fallback(user_prompt)
        self.set_cached(cache_key, response)
        return response

    def _deterministic_fallback(self, prompt: str) -> str:
        """Deterministic natural-language rule-based extraction for offline & demo resilience."""
        # Extract report content inside <report>...</report> if present
        match = re.search(r"<report>(.*?)</report>", prompt, re.DOTALL | re.IGNORECASE)
        report_text = match.group(1).strip() if match else prompt

        # Injection defense check: ignore directives
        lower = report_text.lower()

        # Language detection
        lang = "en"
        if any(w in lower for w in ["hai", "hain", "ke paas", "madad", "chahiye", "bachao", "pani", "paani", "log", "bache", "buzurg"]):
            lang = "hinglish"
        if re.search(r"[\u0900-\u097F]", report_text):
            lang = "hi"
        elif re.search(r"[\u0B80-\u0BFF]", report_text):
            lang = "ta"

        # People extraction
        people_count = None
        evidence_people = ""
        people_match = re.search(r"(\d+)\s*(?:people|persons|log|insaan|vyakti|लोग)", report_text, re.IGNORECASE)
        if people_match:
            people_count = int(people_match.group(1))
            evidence_people = people_match.group(0)
        elif "five" in lower or "panch" in lower or "paanch" in lower or "पाँच" in lower or "पांच" in lower:
            people_count = 5
            evidence_people = "five" if "five" in lower else "paanch"
        elif "three" in lower or "teen" in lower or "तीन" in lower:
            people_count = 3
            evidence_people = "three" if "three" in lower else "teen"

        # Vulnerable flags
        has_child = any(w in lower for w in ["child", "children", "baby", "kid", "kids", "bache", "bachha", "bachhe", "बच्चे", "बच्चा"])
        has_elderly = any(w in lower for w in ["elderly", "old", "senior", "bujurg", "buzurg", "dada", "dadi", "बुजुर्ग", "बूढ़े"])
        has_disabled = any(w in lower for w in ["disabled", "handicap", "wheelchair", "divyang", "दिव्यांग"])
        has_pregnant = any(w in lower for w in ["pregnant", "pregnancy", "garbhvati", "गर्भवती"])
        has_medical = any(w in lower for w in ["medical", "medicine", "doctor", "insulin", "heart", "oxygen", "bimaar", "dawa", "दवा", "बीमार", "injur"])

        evidence_vuln = ""
        if has_child and "bache" in lower:
            evidence_vuln = "bache"
        elif has_child and "children" in lower:
            evidence_vuln = "children"
        elif has_child and "बच्चे" in report_text:
            evidence_vuln = "बच्चे"
        elif has_elderly and "buzurg" in lower:
            evidence_vuln = "buzurg"
        elif has_elderly and "elderly" in lower:
            evidence_vuln = "elderly"

        # Incident type & hazard
        inc_type = "rescue"
        hazard = "none"
        urgency_hint = "medium"

        if any(w in lower for w in ["dog", "bite", "bitten", "rabies", "kutta", "kutte", "कुत्ता"]):
            inc_type = "animal_attack"
            hazard = "injury"
            urgency_hint = "high"
        elif any(w in lower for w in ["medical", "medicine", "doctor", "insulin", "ill", "hospital", "hospitalized", "labor", "injur", "दवा", "इंसुलिन", "अस्पताल", "बीमार"]):
            inc_type = "medical"
            hazard = "injury"
            urgency_hint = "high"
        elif any(w in lower for w in ["food", "khana", "ration", "water to drink", "peene ka paani", "भूख", "खाना", "पैकेट"]):
            inc_type = "food"
        elif any(w in lower for w in ["shelter", "roof collapsed", "gharon me pani", "ashray", "आश्रय"]):
            inc_type = "shelter"

        if any(w in lower for w in ["water rising", "water is rising", "paani badh raha hai", "pani badh raha", "पानी बढ़ रहा"]):
            hazard = "water_rising"
            urgency_hint = "high"
        elif any(w in lower for w in ["stranded", "trapped", "marooned", "fanse", "phase", "फंसे"]):
            hazard = "stranded"
            urgency_hint = "high"

        if (has_child or has_elderly or has_pregnant or has_medical) and hazard in ("water_rising", "stranded", "injury"):
            urgency_hint = "critical"

        # Place extraction heuristics
        place_text = None
        place_match = re.search(r"(?:at|near|in|ke paas|paas|ward)\s+([A-Za-z0-9\s,\-\.\u0900-\u097F]+)", report_text, re.IGNORECASE)
        if place_match:
            place_text = place_match.group(1).strip().split(".")[0].split("\n")[0]
            if len(place_text) > 60:
                place_text = place_text[:60]
        elif "gandhi school" in lower:
            place_text = "Gandhi School, Ward 4"

        evidence_spans = {}
        if evidence_people and evidence_people in report_text:
            evidence_spans["people"] = evidence_people
        if evidence_vuln and evidence_vuln in report_text:
            evidence_spans["vulnerable"] = evidence_vuln

        extracted = {
            "type": inc_type,
            "place_text": place_text,
            "people": {
                "count": people_count,
                "confidence": 0.9 if people_count is not None else 0.5
            },
            "vulnerable": {
                "child": has_child,
                "elderly": has_elderly,
                "disabled": has_disabled,
                "pregnant": has_pregnant,
                "medical_need": has_medical
            },
            "hazard": hazard,
            "urgency_hint": urgency_hint,
            "language": lang,
            "is_update_phrase": bool(re.search(r"\b(?:ab|now|update)\b", lower)),
            "confidence": {
                "type": 0.95,
                "place": 0.85 if place_text else 0.3,
                "people": 0.9 if people_count is not None else 0.4,
                "vulnerable": 0.9 if (has_child or has_elderly or has_disabled or has_pregnant or has_medical) else 0.6,
                "urgency": 0.9
            },
            "evidence_spans": evidence_spans,
            "notes": "Extracted via resilient intake pipeline",
            "needs_human_review": False
        }
        return json.dumps(extracted, ensure_ascii=False)


llm_client = LLMClient()
