from __future__ import annotations

import re
import unicodedata

from core.types import TriageResult


EMERGENCY_RULES = {
    "dor_no_peito": ["dor no peito", "aperto no peito", "enfarte"],
    "respiracao": ["nao consigo respirar", "não consigo respirar", "falta de ar", "nao consigo respirar bem"],
    "consciencia": ["desmaiei", "desmaio", "perda de consciencia", "perda de consciência", "inconsciente"],
    "sangramento": ["sangramento intenso", "hemorragia", "sangro muito"],
    "convulsao": ["convulsao", "convulsão", "ataque epileptico", "ataque epiletico"],
    "avc": ["avc", "derrame", "boca ao lado", "fraqueza num lado"],
    "suicidio": ["suicidio", "suicidar", "quero morrer", "autoagress", "tentei matar", "overdose"],
    "acidente": ["acidente grave", "atropelamento", "queda grave", "queimadura grave"],
}

URGENT_RULES = {
    "febre": ["febre alta", "febre do meu filho", "crianca com febre", "criança com febre"],
    "vomitos": ["vomitos", "vómitos", "vomitar", "vomitei"],
    "panico": ["crise de panico", "crise de pânico", "ataque de panico", "ataque de pânico"],
    "ansiedade": ["crise de ansiedade", "ansiedade forte", "ansiedade"],
    "asma": ["asma", "crise asmatica", "crise asmática", "pieira"],
    "tensao": ["tensao alta", "tensão alta", "pressao alta", "pressão alta"],
    "dor_persistente": ["dor persistente", "dor forte", "dor intensa"],
    "crianca": ["crianca doente", "criança doente", "filho doente", "bebe com febre", "bebé com febre"],
}

PRACTICAL_RULES = {
    "farmacia": ["farmacia", "farmácia"],
    "medicamento": ["medicamento", "remedio", "remédio", "comprimido", "receita"],
    "hospital": ["hospital", "urgencia", "urgência", "consulta urgente", "onde ir", "hospital mais proximo"],
    "contacto": ["telefone", "morada", "rota", "como chegar", "mapa", "perto de mim"],
}

CONVERSATION_HINTS = [
    "nao sei o que fazer",
    "não sei o que fazer",
    "estou confuso",
    "quero falar",
    "nao consigo desligar",
    "não consigo desligar",
    "tive uma discussao",
    "tive uma discussão",
    "stress",
]


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


def compact_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


class TriageEngine:
    def classify(self, query: str) -> TriageResult:
        clean_query = compact_text(query)
        if not clean_query:
            raise ValueError("Escreva o que precisa antes de continuar.")

        normalized = normalize_text(clean_query)
        emergency_matches = self._find_matches(normalized, EMERGENCY_RULES)
        if emergency_matches:
            return TriageResult(
                triage_class="emergency_potential",
                headline="Pode ser uma emergencia",
                summary="Se houver risco imediato, ligue 112.",
                rules_triggered=emergency_matches,
                tags=["emergency"],
            )

        urgent_matches = self._find_matches(normalized, URGENT_RULES)
        practical_matches = self._find_matches(normalized, PRACTICAL_RULES)

        if urgent_matches:
            return TriageResult(
                triage_class="urgent_care",
                headline="Precisa de encaminhamento rapido",
                summary="Veja os contactos oficiais e os recursos mais uteis para o que descreveu.",
                rules_triggered=urgent_matches,
                tags=list(dict.fromkeys(urgent_matches + practical_matches)),
            )

        if practical_matches:
            return TriageResult(
                triage_class="practical_health",
                headline="Opcoes disponiveis",
                summary="Estes recursos podem ajudar a tratar disto de forma pratica.",
                rules_triggered=practical_matches,
                tags=practical_matches,
            )

        conversation_matches = [hint for hint in CONVERSATION_HINTS if hint in normalized]
        return TriageResult(
            triage_class="light_conversation",
            headline="Vamos organizar isto",
            summary="Recebe uma resposta curta e, se quiser, pode continuar de forma estruturada.",
            rules_triggered=conversation_matches,
            tags=["conversation"],
        )

    def _find_matches(self, normalized_query: str, rules: dict[str, list[str]]) -> list[str]:
        matches: list[str] = []
        for rule_name, keywords in rules.items():
            if any(keyword in normalized_query for keyword in (normalize_text(item) for item in keywords)):
                matches.append(rule_name)
        return matches
