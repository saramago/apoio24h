from __future__ import annotations

from core.providers.base import BaseProvider, iso_now


LINES_URL = "https://www.sns.gov.pt/sns-saude-mais/linhas-de-atendimento-gerais/"
SNS_HOME_URL = "https://www.sns.gov.pt/"


class SnsPortalProvider(BaseProvider):
    name = "sns_portal"
    validated = True
    ttl_seconds = 21600

    def fetch(self) -> dict:
        return {
            "updated_at": iso_now(),
            "notes": ["Contactos institucionais obtidos de paginas oficiais do SNS."],
            "items": [
                {
                    "title": "Numero Europeu de Emergencia",
                    "description": "Disponivel 24 horas por dia.",
                    "phone": "112",
                    "url": "tel:112",
                    "source": LINES_URL,
                    "validated": True,
                    "category": "emergency",
                },
                {
                    "title": "SNS 24",
                    "description": "Triagem, aconselhamento e encaminhamento para situacoes nao emergentes.",
                    "phone": "808 24 24 24",
                    "url": "tel:808242424",
                    "source": LINES_URL,
                    "validated": True,
                    "category": "urgent",
                },
                {
                    "title": "Linhas de atendimento gerais",
                    "description": "Pagina oficial do SNS com contactos institucionais e linhas de apoio.",
                    "url": LINES_URL,
                    "source": LINES_URL,
                    "validated": True,
                    "category": "reference",
                },
                {
                    "title": "Portal do SNS",
                    "description": "Acesso ao portal institucional do SNS.",
                    "url": SNS_HOME_URL,
                    "source": SNS_HOME_URL,
                    "validated": True,
                    "category": "reference",
                },
            ],
        }
