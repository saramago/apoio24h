from __future__ import annotations

from core.providers.base import BaseProvider, iso_now


ANF_URL = "https://www.anf.pt/farmacias-portuguesas/rede-de-farmacias/"


class FarmaciasProvider(BaseProvider):
    name = "farmacias_provider"
    validated = False
    ttl_seconds = 21600

    def fetch(self) -> dict:
        raise RuntimeError("Provider de farmacias de servico nao validado para dados em tempo util.")

    def fallback(self) -> dict:
        return {
            "updated_at": iso_now(),
            "items": [
                {
                    "title": "Rede de Farmacias",
                    "description": "Ligacao institucional da rede de farmacias. Disponibilidade de servico nao validada nesta versao.",
                    "url": ANF_URL,
                    "source": ANF_URL,
                    "validated": False,
                    "category": "pharmacy",
                }
            ],
            "notes": ["Disponibilidade de farmacias de servico indisponivel nesta versao."],
        }
