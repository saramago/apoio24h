from __future__ import annotations

from urllib.parse import quote_plus

from core.providers.base import BaseProvider, iso_now


class MapsProvider(BaseProvider):
    name = "maps_provider"
    validated = True
    ttl_seconds = 86400

    def fetch(self) -> dict:
        return {
            "provider": "google_maps_links",
            "updated_at": iso_now(),
            "items": [],
            "notes": ["Links de mapa externos disponiveis."],
        }

    def search_url(self, query: str) -> str:
        return f"https://www.google.com/maps/search/?api=1&query={quote_plus(query)}"

    def directions_url(self, destination: str) -> str:
        return f"https://www.google.com/maps/dir/?api=1&destination={quote_plus(destination)}"
