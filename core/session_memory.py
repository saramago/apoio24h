from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from threading import Lock


def compact_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


FOLLOW_UP_PREFIXES = (
    "em ",
    "para ",
    "com ",
    "mais ",
    "perto ",
    "aberta",
    "aberto",
    "urgente",
    "urgencia",
    "urgência",
    "agora",
    "hoje",
)

FOLLOW_UP_TERMS = {
    "urgente",
    "urgencia",
    "urgência",
    "agora",
    "hoje",
    "lisboa",
    "porto",
    "coimbra",
    "braga",
    "faro",
    "setubal",
    "setúbal",
    "evora",
    "évora",
}


@dataclass
class SessionSnapshot:
    session_id: str
    last_query: str
    triage_class: str
    recent_context: list[str] = field(default_factory=list)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self, resolved_query: str, continued: bool) -> dict:
        return {
            "session_id": self.session_id,
            "last_query": self.last_query,
            "triage_class": self.triage_class,
            "recent_context": self.recent_context[-3:],
            "resolved_query": resolved_query,
            "continued": continued,
        }


class SessionMemoryStore:
    def __init__(self, ttl_seconds: int = 1800) -> None:
        self.ttl_seconds = ttl_seconds
        self._sessions: dict[str, SessionSnapshot] = {}
        self._lock = Lock()

    def ensure_session_id(self, session_id: str | None) -> str:
        clean = compact_text(session_id or "")
        return clean or str(uuid.uuid4())

    def resolve_query(self, session_id: str, query: str) -> tuple[str, dict]:
        clean_query = compact_text(query)
        snapshot = self.get(session_id)
        if not snapshot:
            return clean_query, {
                "session_id": session_id,
                "last_query": None,
                "triage_class": None,
                "recent_context": [],
                "resolved_query": clean_query,
                "continued": False,
            }

        if not self._should_merge(clean_query, snapshot):
            return clean_query, snapshot.to_dict(clean_query, False)

        resolved_query = self._merge_queries(snapshot.last_query, clean_query)
        return resolved_query, snapshot.to_dict(resolved_query, True)

    def remember(self, session_id: str, raw_query: str, triage_class: str, resolved_query: str | None = None) -> None:
        clean_query = compact_text(resolved_query or raw_query)
        if not clean_query:
            return

        with self._lock:
            self._purge_locked()
            previous = self._sessions.get(session_id)
            recent_context = list(previous.recent_context) if previous else []
            recent_context.append(clean_query)
            recent_context = list(dict.fromkeys(item for item in recent_context if item))[-4:]
            self._sessions[session_id] = SessionSnapshot(
                session_id=session_id,
                last_query=clean_query,
                triage_class=triage_class,
                recent_context=recent_context,
                updated_at=time.time(),
            )

    def get(self, session_id: str) -> SessionSnapshot | None:
        with self._lock:
            self._purge_locked()
            return self._sessions.get(session_id)

    def _should_merge(self, clean_query: str, snapshot: SessionSnapshot) -> bool:
        if not clean_query or not snapshot.last_query:
            return False

        lowered = clean_query.lower()
        if lowered == snapshot.last_query.lower():
            return False

        words = lowered.split()
        if len(words) <= 3:
            return True

        if any(lowered.startswith(prefix) for prefix in FOLLOW_UP_PREFIXES):
            return True

        return all(word in FOLLOW_UP_TERMS for word in words)

    def _merge_queries(self, previous_query: str, new_query: str) -> str:
        previous = compact_text(previous_query)
        current = compact_text(new_query)
        if not previous:
            return current
        return compact_text(f"{previous} {current}")

    def _purge_locked(self) -> None:
        now = time.time()
        expired = [
            session_id
            for session_id, snapshot in self._sessions.items()
            if now - snapshot.updated_at > self.ttl_seconds
        ]
        for session_id in expired:
            self._sessions.pop(session_id, None)
