from __future__ import annotations

from core.providers.base import BaseProvider, iso_now


INFARMED_SERVICES_URL = "https://www.infarmed.pt/web/infarmed/servicos-on-line"
INFARMED_SEARCH_URL = "https://www.infarmed.pt/web/infarmed/pesquisa-avancada"


class InfarmedInfomedProvider(BaseProvider):
    name = "infarmed_infomed"
    validated = True
    ttl_seconds = 21600

    def fetch(self) -> dict:
        return {
            "updated_at": iso_now(),
            "items": [
                {
                    "title": "INFOMED",
                    "description": "Base de dados institucional de medicamentos.",
                    "url": INFARMED_SERVICES_URL,
                    "source": INFARMED_SERVICES_URL,
                    "validated": True,
                    "category": "medicine",
                },
                {
                    "title": "Pesquisa de medicamento",
                    "description": "Pesquisa institucional do INFARMED para medicamentos e informacao relacionada.",
                    "url": INFARMED_SEARCH_URL,
                    "source": INFARMED_SERVICES_URL,
                    "validated": True,
                    "category": "medicine",
                },
            ],
            "notes": ["Informacao de medicamentos com base em servicos institucionais do INFARMED."],
        }
