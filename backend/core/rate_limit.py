"""Small, thread-safe request budgets for endpoints with local protection."""

from collections import deque
from math import ceil
from threading import Lock
from time import monotonic

from backend.core.errors import ServiceError


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: int):
        self.limit = limit
        self.window_seconds = window_seconds
        self._accepted: deque[float] = deque()
        self._lock = Lock()

    def check(self) -> None:
        with self._lock:
            now = monotonic()
            while self._accepted and now - self._accepted[0] >= self.window_seconds:
                self._accepted.popleft()
            if len(self._accepted) >= self.limit:
                retry_after = ceil(self.window_seconds - (now - self._accepted[0]))
                raise ServiceError(
                    429,
                    'Please retry shortly.',
                    headers={'Retry-After': str(retry_after)},
                )
            self._accepted.append(now)
