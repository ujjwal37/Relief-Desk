"""Limits around live Gemini calls. Tests can pass a fake clock and a fake sleep."""
import re
import threading
import time
from typing import Callable

from app.llm.ai_queue import PrioritySlots

PHONE = re.compile(r"(?<!\d)(?:\+91[\s-]?)?[6-9]\d{9}(?!\d)")
EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.\w+")
ADVICE = (
    "take this medicine",
    "you should sue",
    "i diagnose",
    "prescribe",
    "this is legal advice",
    "this is medical advice",
)


class Guard:
    def __init__(self, per_minute: float = 30.0, max_in_flight: int = 4, fail_limit: int = 3):
        self.per_minute = per_minute
        self.gap = 60.0 / per_minute if per_minute else 0.0
        self._next = 0.0
        self._lock = threading.Lock()
        self.slots = PrioritySlots(max_in_flight)
        self.fail_limit = fail_limit
        self.failures = 0
        self.opened_at = 0.0
        self.open_for = 30.0
        self.sleep: Callable[[float], None] = time.sleep
        self.now: Callable[[], float] = time.monotonic
        self.last_failure_at = 0.0
        self.last_failure_reason: str = ""
        self.last_success_at = 0.0
        self.last_success_iso: str | None = None
        self.half_open = False
        # Repeated trips back off: 30 s, 2 min, 8 min, capped at 15 min.
        self.base_open = 30.0
        self.max_open = 900.0

    def circuit_open(self) -> bool:
        if self.failures < self.fail_limit:
            return False
        if (self.now() - self.opened_at) < self.open_for:
            return True
        # Half-open: let one call through. If it fails, record_failure re-opens for longer.
        self.failures = self.fail_limit - 1
        self.half_open = True
        return False

    def trip(self, seconds: float) -> None:
        """Open the circuit now, and keep it open for `seconds` (the daily reset)."""
        self.failures = self.fail_limit
        self.opened_at = self.now()
        self.open_for = max(1.0, seconds)

    def wait_turn(self, max_wait: float | None = None) -> None:
        """Pace calls. With `max_wait`, refuse (TimeoutError) rather than wait longer."""
        with self._lock:
            current = self.now()
            delay = 0.0
            if current < self._next:
                delay = self._next - current
            if max_wait is not None and delay > max_wait:
                raise TimeoutError("Model pacing wait too long")
            self._next = max(current, self._next) + self.gap
        if delay:
            self.sleep(delay)

    def record_success(self) -> None:
        from datetime import datetime, timezone

        self.failures = 0
        self.half_open = False
        self.open_for = self.base_open
        self.last_success_at = self.now()
        self.last_success_iso = datetime.now(timezone.utc).isoformat()

    def note_reason(self, reason: str) -> None:
        self.last_failure_at = self.now()
        self.last_failure_reason = reason

    def failing(self, window: float = 600.0) -> bool:
        """True when the newest live result in the window was a failure."""
        if not self.last_failure_at or self.last_failure_at < self.last_success_at:
            return False
        return (self.now() - self.last_failure_at) < window

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= self.fail_limit:
            if self.half_open:
                self.open_for = min(self.max_open, max(self.base_open, self.open_for) * 4)
            self.half_open = False
            self.opened_at = self.now()

    def backoff(self, attempt: int) -> None:
        self.sleep(min(2.0, 0.05 * (2 ** attempt)))


def scrub_pii(text: str) -> str:
    cleaned = PHONE.sub("[redacted-phone]", text or "")
    return EMAIL.sub("[redacted-email]", cleaned)


def strip_advice(text: str) -> str:
    kept = []
    for sentence in re.split(r"(?<=[.!?])\s+", text or ""):
        lower = sentence.lower()
        if any(phrase in lower for phrase in ADVICE):
            continue
        kept.append(sentence)
    return " ".join(part for part in kept if part).strip()
