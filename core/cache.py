from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass
class CacheEntry:
    value: object
    expires_at: float


class TTLCache:
    def __init__(self) -> None:
        self._entries: dict[str, CacheEntry] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> object | None:
        with self._lock:
            entry = self._entries.get(key)
            if not entry:
                return None
            if time.time() >= entry.expires_at:
                self._entries.pop(key, None)
                return None
            return entry.value

    def set(self, key: str, value: object, ttl_seconds: int) -> None:
        with self._lock:
            self._entries[key] = CacheEntry(value=value, expires_at=time.time() + ttl_seconds)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
