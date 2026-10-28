"""In-process sliding-window rate limiting for uploads.

IP addresses are used only as rate-limit keys, hashed with a salt that lives in memory and
changes on every restart. They are never logged or stored (docs/PRIVACY.md).

Single-process only. With several API replicas, move this to a shared store (see
docs/DEPLOYMENT.md, "Scaling").
"""

from __future__ import annotations

import hashlib
import secrets
import threading
import time
from collections import deque


class SlidingWindowLimiter:
    def __init__(self, window_seconds: float = 3600.0):
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()
        self._salt = secrets.token_bytes(16)

    def hashed(self, raw_key: str) -> str:
        return hashlib.sha256(self._salt + raw_key.encode("utf-8")).hexdigest()[:24]

    def allow(self, key: str, limit: int, now: float | None = None) -> tuple[bool, int]:
        """Record a hit for ``key``. Returns ``(allowed, retry_after_seconds)``."""
        now = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            cutoff = now - self.window
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= limit:
                return False, max(1, int(hits[0] + self.window - now))
            hits.append(now)
            if len(self._hits) > 100_000:
                self._evict(cutoff)
            return True, 0

    def _evict(self, cutoff: float) -> None:
        for key in [k for k, v in self._hits.items() if not v or v[-1] <= cutoff]:
            del self._hits[key]

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


upload_limiter = SlidingWindowLimiter()
