"""Priority gate for model calls. A full gate makes the caller wait its turn; it never means fallback.

Lower priority values go first. Ask the desk uses DESK. A report uses its urgency score,
so a critical case is analysed before a low one that arrived earlier.
"""
from __future__ import annotations

import contextlib
import heapq
import itertools
import threading
from typing import Iterator, List, Tuple

DESK = -1000.0
BACKGROUND = 1000.0

_tls = threading.local()


def report_priority(urgency_score: float | None) -> float:
    return -float(urgency_score or 0.0)


def current_priority() -> float:
    return getattr(_tls, "priority", 0.0)


@contextlib.contextmanager
def ai_priority(priority: float) -> Iterator[None]:
    before = getattr(_tls, "priority", None)
    _tls.priority = float(priority)
    try:
        yield
    finally:
        if before is None:
            del _tls.priority
        else:
            _tls.priority = before


class PrioritySlots:
    """At most `size` model calls run at once. Waiters leave in priority order, then arrival order."""

    def __init__(self, size: int = 2):
        self._cond = threading.Condition()
        self._size = max(1, int(size))
        self._busy = 0
        self._waiting: List[Tuple[float, int]] = []
        self._seq = itertools.count()
        self.served: List[float] = []

    @property
    def size(self) -> int:
        return self._size

    @property
    def free(self) -> int:
        with self._cond:
            return self._size - self._busy

    @property
    def waiting(self) -> int:
        with self._cond:
            return len(self._waiting)

    def resize(self, size: int) -> None:
        with self._cond:
            self._size = max(1, int(size))
            self._cond.notify_all()

    def acquire(self, priority: float | None = None, timeout: float | None = None) -> None:
        """Wait for a slot. With `timeout`, give up after that many seconds (TimeoutError)."""
        import time as _time
        mine = (current_priority() if priority is None else float(priority), next(self._seq))
        deadline = None if timeout is None else _time.monotonic() + max(0.0, timeout)
        with self._cond:
            heapq.heappush(self._waiting, mine)
            while not (self._busy < self._size and self._waiting[0] == mine):
                left = None if deadline is None else deadline - _time.monotonic()
                if left is not None and left <= 0:
                    self._waiting.remove(mine)
                    heapq.heapify(self._waiting)
                    self._cond.notify_all()
                    raise TimeoutError("No free model slot in time")
                self._cond.wait(timeout=left)
            heapq.heappop(self._waiting)
            self._busy += 1
            self.served.append(mine[0])
            del self.served[:-50]
            self._cond.notify_all()

    def release(self) -> None:
        with self._cond:
            self._busy = max(0, self._busy - 1)
            self._cond.notify_all()

    @contextlib.contextmanager
    def slot(self, priority: float | None = None) -> Iterator[None]:
        self.acquire(priority)
        try:
            yield
        finally:
            self.release()
