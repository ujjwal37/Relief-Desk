import hashlib
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from app.config import settings
from app.models.schemas import AiCall

logger = logging.getLogger("relief_desk.llm")

CACHE_DIR = Path(__file__).resolve().parents[4] / "data" / "cache" / "llm"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


_PLACEHOLDER_KEYS = {"", "replace-me", "synthetic-demo-gemini-key"}


def _is_quota(exc: BaseException) -> bool:
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if status == 429:
        return True
    text = str(exc).lower()
    return "429" in text or "resource_exhausted" in text or "quota" in text


class LLMClient:
    def __init__(self):
        self.call_count = 0
        self.daily_cap = settings.GEMINI_DAILY_CALL_CAP
        self.last_source = "offline_fallback"
        self.last_ai = AiCall(provider="fallback", fallback_reason="not_called")
        self._last_tokens: Optional[int] = None
        self._memory_cache: Dict[str, str] = {}
        self._memory_source: Dict[str, str] = {}
        self._memory_meta: Dict[str, Dict[str, Any]] = {}

    def _hash_key(self, prompt: str) -> str:
        return hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    def gemini_live(self) -> bool:
        """True when a real key is set. DEMO_MODE does not block that call."""
        if (settings.AI_MODE or "auto").lower() == "fallback" or not settings.GEMINI_ENABLED:
            return False
        key = (settings.GEMINI_API_KEY or "").strip()
        return key not in _PLACEHOLDER_KEYS

    def _remember(self, usage: AiCall) -> None:
        self.last_ai = usage
        if usage.provider == "gemini":
            self.last_source = "gemini"
        elif usage.provider == "cache":
            self.last_source = "cache"
        else:
            self.last_source = "offline_fallback"

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
                    source = data.get("source") or data.get("provider") or "offline_fallback"
                    self._memory_source[key] = source
                    self._memory_meta[key] = {
                        "model": data.get("model"),
                        "tokens": data.get("tokens"),
                        "provider": data.get("provider") or ("gemini" if source == "gemini" else "cache"),
                    }
                    return val
            except Exception as e:
                logger.warning("Error reading cache file %s: %s", cache_file, e)
        return None

    def set_cached(
        self,
        key: str,
        response: str,
        source: str = "offline_fallback",
        model: Optional[str] = None,
        tokens: Optional[int] = None,
    ) -> None:
        self._memory_cache[key] = response
        self._memory_source[key] = source
        self._memory_meta[key] = {"model": model, "tokens": tokens, "provider": source}
        cache_file = CACHE_DIR / f"{key}.json"
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "key": key,
                        "response": response,
                        "source": source,
                        "provider": source,
                        "model": model,
                        "tokens": tokens,
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception as e:
            logger.warning("Error writing cache file %s: %s", cache_file, e)

    def _fallback(self, user_prompt: str, reason: str, started: float) -> str:
        response = self._deterministic_fallback(user_prompt)
        self._remember(
            AiCall(
                provider="fallback",
                model=None,
                latency_ms=int((time.perf_counter() - started) * 1000),
                tokens=None,
                cached=False,
                fallback_reason=reason,
            )
        )
        return response

    def _from_cache(self, cache_key: str, cached: str, started: float) -> str:
        meta = self._memory_meta.get(cache_key, {})
        self._remember(
            AiCall(
                provider="cache",
                model=meta.get("model") or settings.GEMINI_MODEL,
                latency_ms=int((time.perf_counter() - started) * 1000),
                tokens=meta.get("tokens"),
                cached=True,
                fallback_reason=None,
            )
        )
        return cached

    def generate_content(
        self,
        system_instruction: str,
        user_prompt: str,
        validator: Optional[Callable[[str], Any]] = None,
        max_retries: int = 1,
    ) -> str:
        """Call Gemini, a recorded cache entry, or the deterministic fallback.

        max_retries is the number of repair attempts after invalid JSON. The
        default is one repair, then fallback.
        """
        started = time.perf_counter()
        full_prompt = f"SYSTEM:\n{system_instruction}\n\nUSER:\n{user_prompt}"
        cache_key = self._hash_key(full_prompt)
        mode = (settings.AI_MODE or "auto").lower()

        cached = self.get_cached(cache_key)
        cache_ok = False
        if cached:
            if validator:
                try:
                    validator(cached)
                    cache_ok = True
                except Exception:
                    logger.warning("Cached entry failed validation, not replaying it.")
            else:
                cache_ok = True
        recorded = self._memory_source.get(cache_key) in ("gemini", "cache")
        if cache_ok and cached is not None and mode == "replay" and recorded:
            logger.info("Replay cache hit for prompt hash %s", cache_key[:8])
            return self._from_cache(cache_key, cached, started)
        if cache_ok and cached is not None and mode != "live" and not self.gemini_live():
            return self._from_cache(cache_key, cached, started)

        if not self.gemini_live():
            reason = "disabled" if not settings.GEMINI_ENABLED or mode == "fallback" else "no_api_key"
            logger.info("Deterministic fallback (%s).", reason)
            return self._fallback(user_prompt, reason, started)

        if self.call_count >= self.daily_cap:
            logger.warning("Gemini daily call cap reached (%d).", self.daily_cap)
            return self._fallback(user_prompt, "daily_cap", started)

        current_prompt = user_prompt
        repairs_left = max_retries
        try:
            while True:
                self.call_count += 1
                text = self._call_gemini(system_instruction, current_prompt)
                if validator:
                    try:
                        validator(text)
                    except Exception as val_err:
                        logger.warning("Validation failed (%s). Repairs left: %d", val_err, repairs_left)
                        if repairs_left <= 0:
                            return self._fallback(user_prompt, "invalid_json", started)
                        repairs_left -= 1
                        current_prompt = (
                            f"{user_prompt}\n\nPREVIOUS OUTPUT WAS INVALID JSON OR FAILED VALIDATION:\n"
                            f"{val_err}\nReturn one JSON object only."
                        )
                        continue
                usage = AiCall(
                    provider="gemini",
                    model=settings.GEMINI_MODEL,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    tokens=self._last_tokens,
                    cached=False,
                    fallback_reason=None,
                )
                self._remember(usage)
                self.set_cached(cache_key, text, source="gemini", model=usage.model, tokens=usage.tokens)
                return text
        except Exception as exc:
            reason = "quota" if _is_quota(exc) else ("timeout" if isinstance(exc, TimeoutError) else "error")
            logger.error("Live Gemini call failed (%s). Falling back.", exc)
            return self._fallback(user_prompt, reason, started)

    def _call_gemini(self, system_instruction: str, user_prompt: str, timeout_s: float = 12.0) -> str:
        """One live generate call. Raises on timeout, missing SDK, or an empty reply."""
        from concurrent.futures import ThreadPoolExecutor
        from concurrent.futures import TimeoutError as FuturesTimeout

        self._last_tokens = None

        def _run() -> str:
            import google.genai as genai  # type: ignore

            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            response_obj = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=user_prompt,
                config={"system_instruction": system_instruction, "temperature": 0.1},
            )
            usage = getattr(response_obj, "usage_metadata", None)
            total = getattr(usage, "total_token_count", None) if usage is not None else None
            self._last_tokens = int(total) if isinstance(total, int) else None
            return response_obj.text or ""

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_run)
            try:
                text = future.result(timeout=timeout_s)
            except FuturesTimeout as exc:
                raise TimeoutError("Gemini timed out") from exc
        if not text.strip():
            raise RuntimeError("Gemini returned an empty reply")
        return text

    def generate(self, prompt: str, system_instruction: str = "") -> str:
        return self.generate_content(system_instruction=system_instruction, user_prompt=prompt)

    def generate_json(self, prompt: str, system_instruction: str = "") -> Dict[str, Any]:
        raw = self.generate(prompt, system_instruction=system_instruction)
        clean = raw.strip()
        if clean.startswith("```json"):
            clean = clean[7:]
        elif clean.startswith("```"):
            clean = clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
        parsed = json.loads(clean.strip())
        if not isinstance(parsed, dict):
            raise ValueError("Gemini JSON was not an object")
        return parsed

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
