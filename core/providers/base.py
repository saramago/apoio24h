from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core.cache import TTLCache
from core.types import ProviderHealth


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class BaseProvider:
    name = "base_provider"
    validated = False
    ttl_seconds = 1800

    def __init__(self) -> None:
        self.cache = TTLCache()
        self.last_sync_at: str | None = None
        self.last_error: str | None = None
        self.mode = "fallback"
        self.status = "idle"

    def fetch(self) -> Any:
        raise NotImplementedError

    def normalize(self, raw: Any) -> dict:
        return raw

    def validate(self, data: dict) -> bool:
        return bool(data)

    def fallback(self) -> dict:
        return {"items": [], "notes": ["Fonte indisponivel."], "updated_at": None}

    def get_data(self, force_refresh: bool = False) -> dict:
        cached = None if force_refresh else self.cache.get(self.name)
        if cached is not None:
            return cached

        try:
            raw = self.fetch()
            normalized = self.normalize(raw)
            if not self.validate(normalized):
                raise ValueError("Dados invalidos.")
            self.last_error = None
            self.last_sync_at = iso_now()
            self.mode = "live"
            self.status = "ok"
            self.cache.set(self.name, normalized, self.ttl_seconds)
            return normalized
        except Exception as exc:  # noqa: BLE001
            fallback = self.fallback()
            self.last_error = str(exc)
            self.last_sync_at = iso_now()
            self.mode = "fallback"
            self.status = "degraded"
            self.cache.set(self.name, fallback, self.ttl_seconds)
            return fallback

    def health_check(self) -> ProviderHealth:
        return ProviderHealth(
            name=self.name,
            validated=self.validated,
            mode=self.mode,
            status=self.status,
            last_sync_at=self.last_sync_at,
            last_error=self.last_error,
        )
