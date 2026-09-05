"""Hold Canvas responses in memory for a few minutes.

A single question from the host ("what's due, and how much is it worth?") turns into
several Canvas calls that repeat across follow-up questions. Caching for five minutes
keeps a conversation responsive without ever putting deadlines or grades on disk.
The cache lives in the process and dies with it.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Mapping
from typing import Any, Final, TypeVar

DEFAULT_TTL_S: Final[float] = 300.0
MAX_ENTRIES: Final[int] = 256

T = TypeVar("T")


def make_key(route: str, params: Mapping[str, Any] | None = None) -> str:
    """Build a stable cache key from a route and its parameters."""
    if not params:
        return route
    normalised = {k: sorted(v) if isinstance(v, list) else v for k, v in sorted(params.items())}
    return route + "?" + json.dumps(normalised, sort_keys=True, default=str)


class TTLCache:
    """A small thread-safe cache with per-entry expiry."""

    __slots__ = ("_data", "_lock", "ttl")

    def __init__(self, ttl: float = DEFAULT_TTL_S) -> None:
        self.ttl = ttl
        self._data: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        """Return a live cached value, or ``None`` when missing or stale."""
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if expires_at < time.monotonic():
                self._data.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        """Store a value under a key."""
        with self._lock:
            if len(self._data) >= MAX_ENTRIES:
                self._evict_locked()
            self._data[key] = (time.monotonic() + (self.ttl if ttl is None else ttl), value)

    def get_or_set(self, key: str, factory: Any, *, refresh: bool = False, ttl: float | None = None) -> Any:
        """Return the cached value for a key, computing it with *factory* when absent.

        The factory runs outside the lock: a slow Canvas call must not block another
        tool reading an unrelated key.
        """
        if not refresh:
            hit = self.get(key)
            if hit is not None:
                return hit
        value = factory()
        self.set(key, value, ttl)
        return value

    def invalidate(self, prefix: str = "") -> None:
        """Drop every entry, or every entry whose key starts with *prefix*."""
        with self._lock:
            if not prefix:
                self._data.clear()
                return
            for key in [k for k in self._data if k.startswith(prefix)]:
                self._data.pop(key, None)

    def _evict_locked(self) -> None:
        """Drop expired entries, then the oldest, to stay under the size cap."""
        now = time.monotonic()
        for key in [k for k, (expires_at, _) in self._data.items() if expires_at < now]:
            self._data.pop(key, None)
        while len(self._data) >= MAX_ENTRIES:
            oldest = min(self._data, key=lambda k: self._data[k][0])
            self._data.pop(oldest, None)

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)
