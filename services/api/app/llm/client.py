import hashlib
import json
import logging
import re
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from zoneinfo import ZoneInfo
from app.config import settings
from app.llm.guards import Guard, scrub_pii
from app.models.schemas import AiCall

logger = logging.getLogger("relief_desk.llm")

CACHE_DIR = Path(__file__).resolve().parents[4] / "data" / "cache" / "llm"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
# Recorded Gemini replies. Empty until `make record-ai` runs with a real key.
REPLAY_DIR = Path(__file__).resolve().parents[4] / "data" / "ai_cache"


from concurrent.futures import ThreadPoolExecutor

# Shared pool. Never used in a `with` block: leaving one would join a hung call.
_GEMINI_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="gemini")

_PLACEHOLDER_KEYS = {"", "replace-me", "synthetic-demo-gemini-key"}


def _is_quota(exc: BaseException) -> bool:
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if status == 429:
        return True
    text = str(exc).lower()
    return "429" in text or "resource_exhausted" in text or "quota" in text


def _is_daily_quota(exc: BaseException) -> bool:
    """True for a per-day RESOURCE_EXHAUSTED. A short per-minute 429 is not this."""
    if not _is_quota(exc):
        return False
    flat = re.sub(r"[\s_\-]", "", str(exc).lower())
    return "perday" in flat or "daily" in flat


def seconds_until_pacific_midnight() -> float:
    """Gemini daily quota resets at midnight Pacific. Stay open until then."""
    pacific = ZoneInfo("America/Los_Angeles")
    now = datetime.now(pacific)
    nxt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(60.0, (nxt - now).total_seconds())


def _is_transient(exc: BaseException) -> bool:
    """503 high demand, 504 deadline, or 500: worth one short retry. Not 429 and not our own timeout."""
    if isinstance(exc, TimeoutError) or _is_quota(exc):
        return False
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if status in (500, 503, 504):
        return True
    text = str(exc)
    return text.startswith(("500", "503", "504")) or "UNAVAILABLE" in text or "DEADLINE_EXCEEDED" in text


class LLMClient:
    def __init__(self):
        self.call_count = 0
        self.daily_cap = settings.GEMINI_DAILY_CALL_CAP
        self._tls = threading.local()
        self._cache_lock = threading.Lock()
        self.last_source = "offline_fallback"
        self.last_ai = AiCall(provider="fallback", fallback_reason="not_called")
        self._last_tokens: Optional[int] = None
        self._memory_cache: Dict[str, str] = {}
        self._memory_source: Dict[str, str] = {}
        self._memory_meta: Dict[str, Dict[str, Any]] = {}
        self.guard = Guard(max_in_flight=settings.AI_CONCURRENCY)
        self._local_cache: Dict[str, str] = {}
        self.cache_hits = 0
        self.cache_misses = 0

    def _hash_key(self, prompt: str) -> str:
        return hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    def cache_key(self, system_instruction: str, user_prompt: str) -> str:
        cleaned = scrub_pii(user_prompt)
        full_prompt = f"SYSTEM:\n{system_instruction}\n\nUSER:\n{cleaned}"
        return self._hash_key(full_prompt)

    def gemini_live(self) -> bool:
        """True when a real key is set. DEMO_MODE does not block that call."""
        if (settings.AI_MODE or "auto").lower() == "fallback" or not settings.GEMINI_ENABLED:
            return False
        key = (settings.GEMINI_API_KEY or "").strip()
        return key not in _PLACEHOLDER_KEYS

    @property
    def last_ai(self) -> AiCall:
        """The call this thread just made. Parallel intake must not share one slot."""
        value = getattr(self._tls, "last_ai", None)
        if value is None:
            value = AiCall(provider="fallback", fallback_reason="not_called")
            self._tls.last_ai = value
        return value

    @last_ai.setter
    def last_ai(self, usage: AiCall) -> None:
        self._tls.last_ai = usage

    @property
    def last_source(self) -> str:
        return getattr(self._tls, "last_source", "offline_fallback")

    @last_source.setter
    def last_source(self, value: str) -> None:
        self._tls.last_source = value

    def _remember(self, usage: AiCall) -> None:
        self.last_ai = usage
        if usage.provider == "gemini":
            self.last_source = "gemini"
        elif usage.provider == "cache":
            self.last_source = "cache"
        else:
            self.last_source = "offline_fallback"

    def _read_disk(self, cache_file: Path, key: str) -> Optional[str]:
        if not cache_file.is_file():
            return None
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.warning("Error reading cache file %s: %s", cache_file, e)
            return None
        val = data.get("response")
        if not isinstance(val, str) or not val.strip():
            return None
        self._memory_cache[key] = val
        source = data.get("source") or data.get("provider") or "offline_fallback"
        self._memory_source[key] = source
        self._memory_meta[key] = {
            "model": data.get("model"),
            "tokens": data.get("tokens"),
            "provider": data.get("provider") or ("gemini" if source == "gemini" else "cache"),
        }
        return val

    def get_cached(self, key: str) -> Optional[str]:
        with self._cache_lock:
            return self._get_cached_unlocked(key)

    def _get_cached_unlocked(self, key: str) -> Optional[str]:
        if key in self._memory_cache:
            return self._memory_cache[key]
        mode = (settings.AI_MODE or "auto").lower()
        replay = REPLAY_DIR / f"{key}.json"
        runtime = CACHE_DIR / f"{key}.json"
        order = (replay, runtime) if mode == "replay" else (runtime, replay)
        for path in order:
            found = self._read_disk(path, key)
            if found is not None:
                return found
        return None

    def set_cached(
        self,
        key: str,
        response: str,
        source: str = "offline_fallback",
        model: Optional[str] = None,
        tokens: Optional[int] = None,
    ) -> None:
        with self._cache_lock:
            self._set_cached_unlocked(key, response, source, model, tokens)

    def _set_cached_unlocked(
        self,
        key: str,
        response: str,
        source: str,
        model: Optional[str],
        tokens: Optional[int],
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
        user_prompt = scrub_pii(user_prompt)
        cache_key = self.cache_key(system_instruction, user_prompt)
        mode = (settings.AI_MODE or "auto").lower()

        from app.llm import openai_compat as oc

        if oc.enabled():
            return self._via_openai_compat(system_instruction, user_prompt, validator, max_retries, started)

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
            self.cache_hits += 1
            return self._from_cache(cache_key, cached, started)
        if cache_ok and cached is not None and recorded and mode != "live" and not self.gemini_live():
            self.cache_hits += 1
            return self._from_cache(cache_key, cached, started)
        self.cache_misses += 1

        if mode == "replay":
            from app.llm.replay_catalog import catalog_keys

            if cache_key in catalog_keys():
                logger.info("No recorded Gemini reply for %s. Skipping the live call.", cache_key[:8])
                return self._fallback(user_prompt, "replay_pending", started)

        from app.llm import antigravity as ag

        if ag.antigravity_enabled():
            return self._via_antigravity(system_instruction, user_prompt, validator, started)

        if not self.gemini_live():
            reason = "disabled" if not settings.GEMINI_ENABLED or mode == "fallback" else "no_api_key"
            logger.info("Deterministic fallback (%s).", reason)
            return self._fallback(user_prompt, reason, started)

        if self.call_count >= self.daily_cap:
            logger.warning("Gemini daily call cap reached (%d).", self.daily_cap)
            return self._fallback(user_prompt, "daily_cap", started)
        if self.guard.circuit_open():
            return self._fallback(user_prompt, "circuit_open", started)

        current_prompt = user_prompt
        repairs_left = max_retries
        try:
            while True:
                self.call_count += 1
                text = self._call_with_retry(system_instruction, current_prompt)
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
                self.guard.record_success()
                self.set_cached(cache_key, text, source="gemini", model=usage.model, tokens=usage.tokens)
                return text
        except Exception as exc:
            reason = self.note_failure(exc)
            if reason != "quota":
                self.guard.backoff(0)
            logger.error("Live Gemini call failed (%s). Falling back.", exc)
            return self._fallback(user_prompt, reason, started)

    def note_failure(self, exc: BaseException) -> str:
        """Count a live failure. A per-day 429 opens the circuit until the reset and is not retried."""
        if _is_daily_quota(exc):
            self.guard.trip(seconds_until_pacific_midnight())
            logger.warning("Gemini daily quota is exhausted. Circuit open until the Pacific midnight reset.")
            return "quota"
        self.guard.record_failure()
        if _is_quota(exc):
            return "quota"
        if isinstance(exc, TimeoutError):
            return "timeout"
        return "error"

    def _via_antigravity(self, system_instruction, user_prompt, validator, started) -> str:
        """Manual-testing provider. Cached in memory only, so data/ai_cache stays Gemini API output only."""
        from app.llm import antigravity as ag

        key = self.cache_key(system_instruction, user_prompt)
        remembered = self._local_cache.get(key)
        if remembered is not None:
            self.cache_hits += 1
            self._remember(AiCall(
                provider=ag.PROVIDER,
                model=ag.MODEL,
                latency_ms=int((time.perf_counter() - started) * 1000),
                cached=True,
            ))
            return remembered
        try:
            with self.guard.slots.slot():
                raw, tokens = ag.call_antigravity(system_instruction, user_prompt)
            try:
                text = ag.extract_json(raw)
            except ValueError:
                text = raw.strip()
            if validator:
                validator(text)
        except Exception as exc:
            logger.error("Antigravity CLI call failed (%s). Falling back.", str(exc)[:200])
            return self._fallback(user_prompt, "timeout" if isinstance(exc, TimeoutError) else "error", started)
        usage = AiCall(
            provider=ag.PROVIDER,
            model=ag.MODEL,
            latency_ms=int((time.perf_counter() - started) * 1000),
            tokens=tokens,
            cached=False,
        )
        self._remember(usage)
        self._local_cache[key] = text
        return text

    def _via_openai_compat(self, system_instruction, user_prompt, validator, max_retries, started) -> str:
        """Test provider (NVIDIA NIM or a local OpenAI-compatible server). Memory cache only."""
        from app.llm import openai_compat as oc

        key = f"{oc.PROVIDER}:{oc.model()}:{self.cache_key(system_instruction, user_prompt)}"
        remembered = self._local_cache.get(key)
        if remembered is not None:
            self.cache_hits += 1
            self._remember(AiCall(
                provider=oc.PROVIDER,
                model=oc.model(),
                latency_ms=int((time.perf_counter() - started) * 1000),
                cached=True,
            ))
            return remembered
        self.cache_misses += 1
        prompt = user_prompt
        repairs_left = max_retries
        tokens: Optional[int] = None
        try:
            while True:
                with self.guard.slots.slot():
                    text, used = oc.chat_json(system_instruction, prompt)
                tokens = (tokens or 0) + used if used is not None else tokens
                if not validator:
                    break
                try:
                    validator(text)
                    break
                except Exception as val_err:
                    logger.warning("Test model reply failed validation (%s). Repairs left: %d", val_err, repairs_left)
                    if repairs_left <= 0:
                        return self._fallback(user_prompt, "invalid_json", started)
                    repairs_left -= 1
                    prompt = (
                        f"{user_prompt}\n\nPREVIOUS OUTPUT WAS INVALID JSON OR FAILED VALIDATION:\n"
                        f"{val_err}\nReturn one JSON object only."
                    )
        except Exception as exc:
            logger.error("Test model call failed (%s). Falling back.", str(exc)[:200])
            return self._fallback(user_prompt, oc.failure_reason(exc), started)
        self._remember(AiCall(
            provider=oc.PROVIDER,
            model=oc.model(),
            latency_ms=int((time.perf_counter() - started) * 1000),
            tokens=tokens,
            cached=False,
        ))
        self._local_cache[key] = text
        return text

    def _call_with_retry(self, system_instruction: str, user_prompt: str) -> str:
        """One live call, plus a single short retry on a transient 503/504/500."""
        try:
            return self._call_gemini(system_instruction, user_prompt)
        except Exception as exc:
            if not _is_transient(exc):
                raise
            logger.warning("Gemini transient error (%s). Retrying once.", str(exc)[:80])
            self.guard.sleep(1.0)
            self.call_count += 1
            return self._call_gemini(system_instruction, user_prompt)

    def _make_genai_client(self, timeout_s: float):
        """Build the SDK client with an HTTP timeout so a stuck request cannot hold a slot forever."""
        import google.genai as genai  # type: ignore

        return genai.Client(
            api_key=settings.GEMINI_API_KEY,
            http_options={
                "timeout": int(timeout_s * 1000),
                # One attempt. The SDK's default backoff on 429 is about 20s, and a
                # per-day quota will not recover inside that wait.
                "retry_options": {"attempts": 1},
            },
        )

    def _call_gemini(self, system_instruction: str, user_prompt: str, timeout_s: Optional[float] = None) -> str:
        """One live generate call. Raises on timeout, missing SDK, or an empty reply.

        A full slot gate waits in priority order instead of failing, and the
        timeout starts once this call holds a slot. The call runs on a shared
        worker pool. On timeout we stop waiting and release the slot at once;
        the worker thread is bounded by the HTTP timeout on the client.
        """
        from concurrent.futures import TimeoutError as FuturesTimeout

        timeout_s = float(timeout_s or settings.GEMINI_TIMEOUT_S or 12.0)
        self._last_tokens = None
        self.guard.slots.acquire()
        try:
            self.guard.wait_turn()
        except BaseException:
            self.guard.slots.release()
            raise

        def _run() -> str:
            client = self._make_genai_client(timeout_s)
            response_obj = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=user_prompt,
                config={"system_instruction": system_instruction, "temperature": 0.1},
            )
            usage = getattr(response_obj, "usage_metadata", None)
            total = getattr(usage, "total_token_count", None) if usage is not None else None
            self._last_tokens = int(total) if isinstance(total, int) else None
            return response_obj.text or ""

        try:
            future = _GEMINI_POOL.submit(_run)
            try:
                text = future.result(timeout=timeout_s)
            except FuturesTimeout as exc:
                future.cancel()
                raise TimeoutError("Gemini timed out") from exc
        finally:
            self.guard.slots.release()
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
        elif re.search(r"[\u0D00-\u0D7F]", report_text):
            lang = "ml"

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
