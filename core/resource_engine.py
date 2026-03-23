from __future__ import annotations

import math
import unicodedata
from typing import Any

from core.types import ActionLink, ResourceItem, TriageResult


REGION_ALIASES = {
    "lisboa": ("lisboa",),
    "porto": ("porto",),
    "coimbra": ("coimbra",),
    "braga": ("braga",),
    "faro": ("faro", "algarve"),
    "setubal": ("setubal", "setúbal"),
    "evora": ("evora", "évora"),
    "aveiro": ("aveiro",),
}


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


class ResourceEngine:
    def __init__(self, providers: dict[str, object]) -> None:
        self.providers = providers

    def build(self, triage_result: TriageResult, query: str, location: dict | None = None) -> dict[str, Any]:
        sns_portal = self.providers["sns_portal"].get_data()
        sns_transparencia = self.providers["sns_transparencia"].get_data()
        infarmed = self.providers["infarmed_infomed"].get_data()
        farmacias = self.providers["farmacias_provider"].get_data()
        maps = self.providers["maps_provider"]

        region_hint = self._extract_region_hint(query, location)
        resources: list[ResourceItem] = []
        actions: list[ActionLink] = []
        notes: list[str] = []

        if triage_result.triage_class == "emergency_potential":
            actions.extend(
                [
                    ActionLink(label="Ligar 112", url="tel:112", style="primary", phone="112", external=False),
                    ActionLink(
                        label="Ver urgencias proximas",
                        url=maps.search_url(self._map_query("urgencia hospitalar", region_hint)),
                        style="secondary",
                    ),
                ]
            )
            resources.extend(self._pick_seed_resources(sns_transparencia, "urgency", region_hint, limit=3))
            resources.extend(self._pick_sns_contacts(sns_portal, {"emergency", "urgent"}))
            notes.append("Se houver risco imediato, ligue 112.")

        elif triage_result.triage_class == "urgent_care":
            actions.extend(
                [
                    ActionLink(label="Ligar SNS 24", url="tel:808242424", style="primary", phone="808 24 24 24", external=False),
                    ActionLink(
                        label="Ver urgencias proximas",
                        url=maps.search_url(self._map_query("urgencia hospitalar", region_hint)),
                    ),
                ]
            )
            resources.extend(self._pick_seed_resources(sns_transparencia, "urgency", region_hint, limit=4))
            resources.extend(self._pick_sns_contacts(sns_portal, {"urgent", "reference"}))
            notes.append("Em caso de agravamento, use 112 ou SNS 24.")
            if self._mentions_medicine(query):
                resources.extend(self._pick_by_category(infarmed, "medicine"))
            if self._mentions_pharmacy(query):
                resources.extend(self._pick_by_category(farmacias, "pharmacy"))
                notes.extend(farmacias.get("notes", []))

        elif triage_result.triage_class == "practical_health":
            actions.append(
                ActionLink(
                    label="Abrir mapa",
                    url=maps.search_url(self._map_query("saude", region_hint)),
                    style="primary",
                )
            )
            if self._mentions_hospital(query):
                resources.extend(self._pick_seed_resources(sns_transparencia, "hospital", region_hint, limit=4))
                actions.append(
                    ActionLink(
                        label="Ver hospitais no mapa",
                        url=maps.search_url(self._map_query("hospital", region_hint)),
                    )
                )
            if self._mentions_urgency(query):
                resources.extend(self._pick_seed_resources(sns_transparencia, "urgency", region_hint, limit=4))
                actions.append(
                    ActionLink(
                        label="Ver urgencias no mapa",
                        url=maps.search_url(self._map_query("urgencia hospitalar", region_hint)),
                    )
                )
            if self._mentions_medicine(query):
                resources.extend(self._pick_by_category(infarmed, "medicine"))
            if self._mentions_pharmacy(query):
                resources.extend(self._pick_by_category(farmacias, "pharmacy"))
                actions.append(
                    ActionLink(
                        label="Ver farmacias no mapa",
                        url=maps.search_url(self._map_query("farmacia", region_hint)),
                    )
                )
                notes.extend(farmacias.get("notes", []))
            resources.extend(self._pick_sns_contacts(sns_portal, {"reference"}))

        else:
            notes.append("A conversa paga so aparece em situacoes nao urgentes.")

        source_updates = {
            "sns_portal": sns_portal.get("updated_at"),
            "sns_transparencia": sns_transparencia.get("updated_at"),
            "infarmed_infomed": infarmed.get("updated_at"),
            "farmacias_provider": farmacias.get("updated_at"),
        }

        return {
            "region_hint": region_hint,
            "actions": [action.to_dict() for action in actions],
            "resources": [item.to_dict() for item in resources],
            "notes": list(dict.fromkeys(notes)),
            "source_updates": source_updates,
        }

    def _pick_sns_contacts(self, dataset: dict, categories: set[str]) -> list[ResourceItem]:
        items: list[ResourceItem] = []
        for raw in dataset.get("items", []):
            if raw.get("category") in categories:
                items.append(
                    ResourceItem(
                        title=raw["title"],
                        description=raw["description"],
                        url=raw.get("url"),
                        phone=raw.get("phone"),
                        source="sns_portal",
                        validated=bool(raw.get("validated")),
                        updated_at=dataset.get("updated_at"),
                        category=raw.get("category", "reference"),
                    )
                )
        return items

    def _pick_by_category(self, dataset: dict, category: str) -> list[ResourceItem]:
        items: list[ResourceItem] = []
        for raw in dataset.get("items", []):
            if raw.get("category") == category:
                items.append(
                    ResourceItem(
                        title=raw["title"],
                        description=raw["description"],
                        url=raw.get("url"),
                        phone=raw.get("phone"),
                        source=dataset.get("source_url", category),
                        validated=bool(raw.get("validated")),
                        updated_at=dataset.get("updated_at"),
                        category=category,
                    )
                )
        return items

    def _pick_seed_resources(self, dataset: dict, category: str, region_hint: str | None, limit: int) -> list[ResourceItem]:
        candidates = [item for item in dataset.get("items", []) if item.get("category") == category]
        if region_hint:
            regional = [item for item in candidates if normalize_text(item.get("city", "")) == region_hint]
            if regional:
                candidates = regional

        items: list[ResourceItem] = []
        for raw in candidates[:limit]:
            items.append(
                ResourceItem(
                    title=raw["title"],
                    description=raw["description"],
                    url=raw.get("url"),
                    region=raw.get("city"),
                    source="sns_transparencia",
                    validated=True,
                    updated_at=dataset.get("updated_at"),
                    category=category,
                )
            )
        return items

    def _extract_region_hint(self, query: str, location: dict | None) -> str | None:
        normalized_query = normalize_text(query)
        for region, aliases in REGION_ALIASES.items():
            if any(alias in normalized_query for alias in aliases):
                return region

        if location and location.get("latitude") is not None and location.get("longitude") is not None:
            latitude = float(location["latitude"])
            longitude = float(location["longitude"])
            return self._nearest_region(latitude, longitude)
        return None

    def _nearest_region(self, latitude: float, longitude: float) -> str | None:
        facilities = self.providers["sns_transparencia"].get_data().get("items", [])
        anchors = {}
        for item in facilities:
            city = normalize_text(item.get("city", ""))
            if city not in anchors:
                anchors[city] = (item.get("lat"), item.get("lon"))
        best_region = None
        best_distance = None
        for region, coords in anchors.items():
            lat, lon = coords
            if lat is None or lon is None:
                continue
            distance = math.sqrt((latitude - lat) ** 2 + (longitude - lon) ** 2)
            if best_distance is None or distance < best_distance:
                best_region = region
                best_distance = distance
        return best_region

    def _map_query(self, label: str, region_hint: str | None) -> str:
        if region_hint:
            return f"{label} {region_hint}"
        return f"{label} perto de mim"

    def _mentions_medicine(self, query: str) -> bool:
        normalized = normalize_text(query)
        return any(term in normalized for term in ("medicamento", "remedio", "remedio", "farmaco", "receita"))

    def _mentions_pharmacy(self, query: str) -> bool:
        normalized = normalize_text(query)
        return "farmacia" in normalized

    def _mentions_hospital(self, query: str) -> bool:
        normalized = normalize_text(query)
        return any(term in normalized for term in ("hospital", "internamento", "consulta", "especialidade"))

    def _mentions_urgency(self, query: str) -> bool:
        normalized = normalize_text(query)
        return any(
            term in normalized
            for term in ("urgencia", "urgente", "febre alta", "vomito", "vomitos", "crise de ansiedade", "crise de panico", "sns 24")
        )
