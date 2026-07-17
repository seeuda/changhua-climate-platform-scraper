"""Global rate limiter shared across threads.

Per-thread sleep() does not bound the aggregate request rate: with 3
workers each sleeping 2s, requests hit the server every ~0.67s. This
limiter serializes the *interval between any two requests* process-wide.
"""

import threading
import time


class RateLimiter:
    """Enforce a minimum interval between consecutive acquisitions."""

    def __init__(self, min_interval: float = 2.0):
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self._last_request = 0.0

    def acquire(self):
        """Block until at least min_interval has passed since the last acquire."""
        with self._lock:
            now = time.monotonic()
            wait = self._last_request + self.min_interval - now
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.monotonic()


# Shared instance: scraping and downloading hit the same host family,
# so they share one budget.
GLOBAL_RATE_LIMITER = RateLimiter(min_interval=2.0)
