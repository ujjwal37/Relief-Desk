import logging
import time
from collections import defaultdict
from typing import Dict, List, Tuple
from app.config import settings

logger = logging.getLogger("relief_desk.ratelimit")


class RateLimiter:
    def __init__(self, max_per_hour: int = 10, window_seconds: int = 3600):
        self.max_per_hour = max_per_hour
        self.window_seconds = window_seconds
        self._history: Dict[str, List[float]] = defaultdict(list)

    def check_and_record(self, source_id: str, current_time: float = None) -> Tuple[bool, int]:
        """Checks rate limit for source_id. Returns (is_rate_limited, count_in_window).
        Never deletes requests; only flags them."""
        now = current_time or time.time()
        window_start = now - self.window_seconds

        # Clean old timestamps
        history = [ts for ts in self._history[source_id] if ts > window_start]
        history.append(now)
        self._history[source_id] = history

        count = len(history)
        is_limited = count > self.max_per_hour
        if is_limited:
            logger.warning(
                "Source '%s' exceeded rate limit (%d > %d in window). Tagged as rate_limited.",
                source_id, count, self.max_per_hour
            )
        return is_limited, count

    def reset(self):
        self._history.clear()


rate_limiter = RateLimiter(max_per_hour=settings.RATE_LIMIT_REPORTS_PER_HOUR)
