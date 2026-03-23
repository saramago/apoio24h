from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from threading import Lock


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class Observability:
    def __init__(self) -> None:
        self._lock = Lock()
        self._events = Counter()
        self._queries = Counter()
        self._source_errors = defaultdict(list)

    def record_event(self, name: str) -> None:
        with self._lock:
            self._events[name] += 1

    def record_query(self, query: str) -> None:
        cleaned = " ".join((query or "").strip().split())[:120]
        if not cleaned:
            return
        with self._lock:
            self._queries[cleaned] += 1

    def record_source_error(self, source_name: str, message: str) -> None:
        with self._lock:
            self._source_errors[source_name].append({"at": iso_now(), "message": message[:300]})
            self._source_errors[source_name] = self._source_errors[source_name][-20:]

    def snapshot(self, provider_health: list[dict]) -> dict:
        with self._lock:
            return {
                "generated_at": iso_now(),
                "events": dict(self._events),
                "top_queries": [{"query": key, "count": value} for key, value in self._queries.most_common(12)],
                "source_errors": dict(self._source_errors),
                "providers": provider_health,
            }
