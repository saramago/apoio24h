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
        requires_location = self._requires_location(triage_result, query, region_hint, location)
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
            resources.extend(self._build_emergency_actions(sns_transparencia, sns_portal, maps, region_hint))
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
            resources.extend(self._build_urgent_actions(query, sns_transparencia, sns_portal, infarmed, farmacias, maps, region_hint))
            notes.append("Em caso de agravamento, use 112 ou SNS 24.")
            if self._mentions_pharmacy(query):
                notes.extend(farmacias.get("notes", []))

        elif triage_result.triage_class == "practical_health":
            resources.extend(self._build_practical_actions(query, sns_transparencia, sns_portal, infarmed, farmacias, maps, region_hint))
            if self._mentions_pharmacy(query):
                notes.extend(farmacias.get("notes", []))

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
            "location_label": self._format_region_label(region_hint),
            "requires_location": requires_location,
            "actions": [action.to_dict() for action in actions],
            "resources": [item.to_dict() for item in resources],
            "notes": list(dict.fromkeys(notes)),
            "source_updates": source_updates,
        }

    def _build_emergency_actions(self, sns_transparencia: dict, sns_portal: dict, maps, region_hint: str | None) -> list[ResourceItem]:
        urgent_resources = self._pick_seed_resources(sns_transparencia, "urgency", region_hint, limit=2)
        sns_contacts = self._pick_sns_contacts(sns_portal, {"urgent"})
        items: list[ResourceItem] = [
            self._make_action_item(
                title="Ligar 112",
                description="Iniciar chamada imediata para emergencia medica.",
                url="tel:112",
                phone="112",
                category="emergency",
                source="sns_portal",
            ),
            self._make_action_item(
                title="Ver urgencias proximas",
                description="Abrir mapa com urgencias hospitalares na sua zona.",
                url=maps.search_url(self._map_query("urgencia hospitalar", region_hint)),
                category="urgency",
                source="maps_provider",
            ),
        ]
        if urgent_resources:
            first_urgency = urgent_resources[0]
            items.append(
                self._make_action_item(
                    title="Abrir rota para urgencia",
                    description="Abrir rota para a opcao mais proxima disponivel.",
                    url=maps.directions_url(first_urgency.region or "urgencia hospitalar"),
                    category="urgency",
                    source="maps_provider",
                    region=first_urgency.region,
                )
            )
        if sns_contacts:
            items.append(
                self._make_action_item(
                    title="Ligar SNS 24",
                    description="Usar a linha oficial para triagem nao emergente, se a situacao estiver estavel.",
                    url=sns_contacts[0].url or "tel:808242424",
                    phone=sns_contacts[0].phone,
                    category="urgent",
                    source="sns_portal",
                )
            )
        return items

    def _build_urgent_actions(
        self,
        query: str,
        sns_transparencia: dict,
        sns_portal: dict,
        infarmed: dict,
        farmacias: dict,
        maps,
        region_hint: str | None,
    ) -> list[ResourceItem]:
        items: list[ResourceItem] = [
            self._make_action_item(
                title="Ligar SNS 24",
                description="Iniciar contacto oficial para triagem e encaminhamento.",
                url="tel:808242424",
                phone="808 24 24 24",
                category="urgent",
                source="sns_portal",
            ),
            self._make_action_item(
                title="Ver urgencias proximas",
                description="Abrir mapa com urgencias hospitalares na sua zona.",
                url=maps.search_url(self._map_query("urgencia hospitalar", region_hint)),
                category="urgency",
                source="maps_provider",
            ),
        ]
        if self._mentions_medicine(query):
            items.append(
                self._make_action_item(
                    title="Pesquisar medicamento",
                    description="Abrir a pesquisa institucional de medicamentos.",
                    url=self._first_url_for_category(infarmed, "medicine"),
                    category="medicine",
                    source="infarmed_infomed",
                )
            )
        if self._mentions_pharmacy(query) or self._mentions_medicine(query):
            items.append(
                self._make_action_item(
                    title="Ver farmacias proximas",
                    description="Abrir mapa com farmacias perto de si.",
                    url=maps.search_url(self._map_query("farmacia", region_hint)),
                    category="pharmacy",
                    source="maps_provider",
                )
            )
        items.append(
            self._make_action_item(
                title="Ver informacao oficial",
                description="Abrir a pagina institucional do SNS com contactos e orientacao.",
                url=self._first_url_for_category(sns_portal, "reference"),
                category="reference",
                source="sns_portal",
            )
        )
        return items

    def _build_practical_actions(
        self,
        query: str,
        sns_transparencia: dict,
        sns_portal: dict,
        infarmed: dict,
        farmacias: dict,
        maps,
        region_hint: str | None,
    ) -> list[ResourceItem]:
        if self._mentions_medicine(query):
            return [
                self._make_action_item(
                    title="Pesquisar medicamento",
                    description="Abrir a pesquisa oficial de medicamentos.",
                    url=self._last_url_for_category(infarmed, "medicine"),
                    category="medicine",
                    source="infarmed_infomed",
                ),
                self._make_action_item(
                    title="Ver farmacias proximas",
                    description="Abrir mapa com farmacias perto de si.",
                    url=maps.search_url(self._map_query("farmacia", region_hint)),
                    category="pharmacy",
                    source="maps_provider",
                ),
                self._make_action_item(
                    title="Contactar SNS 24",
                    description="Iniciar chamada para esclarecimento e encaminhamento.",
                    url="tel:808242424",
                    phone="808 24 24 24",
                    category="urgent",
                    source="sns_portal",
                ),
                self._make_action_item(
                    title="Ver informacao oficial",
                    description="Abrir a pagina institucional do INFARMED.",
                    url=self._first_url_for_category(infarmed, "medicine"),
                    category="reference",
                    source="infarmed_infomed",
                ),
            ]

        if self._mentions_pharmacy(query):
            items = [
                self._make_action_item(
                    title="Ver farmacias proximas",
                    description="Abrir mapa com farmacias perto de si.",
                    url=maps.search_url(self._map_query("farmacia", region_hint)),
                    category="pharmacy",
                    source="maps_provider",
                ),
                self._make_action_item(
                    title="Contactar SNS 24",
                    description="Iniciar chamada se precisar de orientacao adicional.",
                    url="tel:808242424",
                    phone="808 24 24 24",
                    category="urgent",
                    source="sns_portal",
                ),
                self._make_action_item(
                    title="Ver informacao oficial",
                    description="Abrir a pagina institucional da rede de farmacias.",
                    url=self._first_url_for_category(farmacias, "pharmacy"),
                    category="reference",
                    source="farmacias_provider",
                    validated=False,
                ),
            ]
            return items

        if self._mentions_hospital(query):
            hospitals = self._pick_seed_resources(sns_transparencia, "hospital", region_hint, limit=1)
            first_hospital = hospitals[0] if hospitals else None
            return [
                self._make_action_item(
                    title="Ver hospitais proximos",
                    description="Abrir mapa com hospitais na sua zona.",
                    url=maps.search_url(self._map_query("hospital", region_hint)),
                    category="hospital",
                    source="maps_provider",
                ),
                self._make_action_item(
                    title="Abrir rota",
                    description="Abrir rota para o hospital mais relevante na zona.",
                    url=maps.directions_url(first_hospital.region or "hospital") if first_hospital else maps.directions_url("hospital"),
                    category="hospital",
                    source="maps_provider",
                    region=first_hospital.region if first_hospital else None,
                ),
                self._make_action_item(
                    title="Ligar SNS 24",
                    description="Confirmar o encaminhamento antes de se deslocar, se necessario.",
                    url="tel:808242424",
                    phone="808 24 24 24",
                    category="urgent",
                    source="sns_portal",
                ),
                self._make_action_item(
                    title="Ver portal SNS",
                    description="Abrir informacao institucional adicional.",
                    url=self._first_url_for_category(sns_portal, "reference"),
                    category="reference",
                    source="sns_portal",
                ),
            ]

        if self._mentions_urgency(query):
            urgencies = self._pick_seed_resources(sns_transparencia, "urgency", region_hint, limit=1)
            first_urgency = urgencies[0] if urgencies else None
            return [
                self._make_action_item(
                    title="Ver urgencias proximas",
                    description="Abrir mapa com urgencias hospitalares na sua zona.",
                    url=maps.search_url(self._map_query("urgencia hospitalar", region_hint)),
                    category="urgency",
                    source="maps_provider",
                ),
                self._make_action_item(
                    title="Abrir rota",
                    description="Abrir rota para a urgencia mais relevante na zona.",
                    url=maps.directions_url(first_urgency.region or "urgencia hospitalar") if first_urgency else maps.directions_url("urgencia hospitalar"),
                    category="urgency",
                    source="maps_provider",
                    region=first_urgency.region if first_urgency else None,
                ),
                self._make_action_item(
                    title="Ligar SNS 24",
                    description="Confirmar o melhor encaminhamento antes de sair, se necessario.",
                    url="tel:808242424",
                    phone="808 24 24 24",
                    category="urgent",
                    source="sns_portal",
                ),
                self._make_action_item(
                    title="Ver portal SNS",
                    description="Abrir informacao institucional adicional.",
                    url=self._first_url_for_category(sns_portal, "reference"),
                    category="reference",
                    source="sns_portal",
                ),
            ]

        return [
            self._make_action_item(
                title="Ver recursos no mapa",
                description="Abrir mapa com recursos de saude proximos.",
                url=maps.search_url(self._map_query("saude", region_hint)),
                category="reference",
                source="maps_provider",
            ),
            self._make_action_item(
                title="Ligar SNS 24",
                description="Usar a linha oficial para esclarecer o que fazer agora.",
                url="tel:808242424",
                phone="808 24 24 24",
                category="urgent",
                source="sns_portal",
            ),
            self._make_action_item(
                title="Ver portal SNS",
                description="Abrir informacao institucional adicional.",
                url=self._first_url_for_category(sns_portal, "reference"),
                category="reference",
                source="sns_portal",
            ),
        ]

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

    def _first_url_for_category(self, dataset: dict, category: str) -> str:
        for raw in dataset.get("items", []):
            if raw.get("category") == category and raw.get("url"):
                return raw["url"]
        return dataset.get("source_url") or "https://www.sns.gov.pt/"

    def _last_url_for_category(self, dataset: dict, category: str) -> str:
        matching = [raw for raw in dataset.get("items", []) if raw.get("category") == category and raw.get("url")]
        if matching:
            return matching[-1]["url"]
        return self._first_url_for_category(dataset, category)

    def _make_action_item(
        self,
        title: str,
        description: str,
        url: str | None,
        category: str,
        source: str,
        phone: str | None = None,
        region: str | None = None,
        validated: bool = True,
    ) -> ResourceItem:
        return ResourceItem(
            title=title,
            description=description,
            url=url,
            phone=phone,
            region=region,
            source=source,
            validated=validated,
            category=category,
        )

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
        if location and location.get("label"):
            normalized_label = normalize_text(location["label"])
            for region, aliases in REGION_ALIASES.items():
                if normalized_label == region or any(alias in normalized_label for alias in aliases):
                    return region

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

    def _requires_location(self, triage_result: TriageResult, query: str, region_hint: str | None, location: dict | None) -> bool:
        if region_hint:
            return False
        if location and (location.get("latitude") is not None or location.get("label")):
            return False
        if triage_result.triage_class in {"emergency_potential", "urgent_care"}:
            return True
        if triage_result.triage_class == "practical_health":
            return any(
                (
                    self._mentions_medicine(query),
                    self._mentions_pharmacy(query),
                    self._mentions_hospital(query),
                    self._mentions_urgency(query),
                )
            )
        return False

    def _format_region_label(self, region_hint: str | None) -> str | None:
        if not region_hint:
            return None
        return region_hint[:1].upper() + region_hint[1:]

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
