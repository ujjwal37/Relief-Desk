"""Token bucket in front of Gemini calls from the live demo and a judge's own report.

The wait is the real gap until the next allowed call (GEMINI_RPM, default 8).
Nothing sleeps just to look busy.
"""
from __future__ import annotations

import threading
import time
from typing import Optional

from app.config import settings

LIMIT_MESSAGE = "Gemini is at its free limit right now; try again in a minute."


class GeminiPacer:
    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._next = 0.0
        self.waiting = 0

    def acquire(self, max_wait: Optional[float] = None) -> int:
        """Block until this call may start. Returns the queue position it held (1 = next)."""
        rpm = int(getattr(settings, "GEMINI_RPM", 8) or 8)
        if rpm <= 0:
            return 0
        gap = 60.0 / float(rpm)
        with self._cond:
            self.waiting += 1
            position = self.waiting
            try:
                while True:
                    now = time.monotonic()
                    delay = self._next - now
                    if delay <= 0:
                        self._next = now + gap
                        return position
                    if max_wait is not None and delay > max_wait:
                        raise TimeoutError(LIMIT_MESSAGE)
                    self._cond.wait(timeout=delay)
            finally:
                self.waiting = max(0, self.waiting - 1)
                self._cond.notify_all()


gemini_pacer = GeminiPacer()


class JudgeLimit:
    """Per-IP cap for a judge typing their own report. 3 a minute, 20 a day."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits: dict[str, list[float]] = {}

    def allow(self, ip: str) -> bool:
        now = time.monotonic()
        day = 24 * 60 * 60
        minute = 60.0
        key = ip or "local"
        with self._lock:
            stamps = [t for t in self._hits.get(key, []) if now - t < day]
            if sum(1 for t in stamps if now - t < minute) >= 3 or len(stamps) >= 20:
                self._hits[key] = stamps
                return False
            stamps.append(now)
            self._hits[key] = stamps
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


judge_limit = JudgeLimit()


def should_pace() -> bool:
    import threading
    return bool(getattr(threading.current_thread(), "rd_pace_gemini", False))


def set_pace(on: bool) -> None:
    import threading
    threading.current_thread().rd_pace_gemini = bool(on)  # type: ignore[attr-defined]


def forbid_replay(on: bool) -> None:
    """A judge's own words must not be answered from a recorded file."""
    from app.llm.client import llm_client
    llm_client._tls.forbid_replay = bool(on)


def replay_forbidden() -> bool:
    from app.llm.client import llm_client
    return bool(getattr(llm_client._tls, "forbid_replay", False))
