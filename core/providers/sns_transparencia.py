from __future__ import annotations

import json

from core.config import BASE_DIR
from core.providers.base import BaseProvider, iso_now


FALLBACK_SOURCE_URL = "https://transparencia.sns.gov.pt/"


class SnsTransparenciaProvider(BaseProvider):
    name = "sns_transparencia"
    validated = True
    ttl_seconds = 21600

    def fetch(self) -> dict:
        seed_path = BASE_DIR / "data" / "sns_facilities_seed.json"
        data = json.loads(seed_path.read_text(encoding="utf-8"))
        data["updated_at"] = iso_now()
        data["notes"] = [
            "Catalogo de apoio para urgencias e hospitais. Confirmar detalhes antes de se deslocar.",
        ]
        return data

    def validate(self, data: dict) -> bool:
        return bool(data.get("items"))

    def fallback(self) -> dict:
        return {
            "updated_at": iso_now(),
            "source_url": FALLBACK_SOURCE_URL,
            "items": [],
            "notes": ["Catalogo de urgencias indisponivel."],
        }
