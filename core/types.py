from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


TRIAGE_CLASSES = (
    "emergency_potential",
    "urgent_care",
    "practical_health",
    "light_conversation",
)


@dataclass
class ActionLink:
    label: str
    url: str
    style: str = "secondary"
    phone: str | None = None
    external: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ResourceItem:
    title: str
    description: str
    source: str
    validated: bool
    url: str | None = None
    phone: str | None = None
    region: str | None = None
    updated_at: str | None = None
    category: str = "resource"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TriageResult:
    triage_class: str
    headline: str
    summary: str
    rules_triggered: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProviderHealth:
    name: str
    validated: bool
    mode: str
    status: str
    last_sync_at: str | None
    last_error: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
