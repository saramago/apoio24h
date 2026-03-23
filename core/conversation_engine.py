from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from threading import Lock
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from core.config import Settings
from core.types import ActionLink


def compact_text(value: str) -> str:
    return " ".join((value or "").strip().split())


@dataclass
class ConversationSession:
    id: str
    original_query: str
    previous_response_id: str | None = None


class ConversationEngine:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._sessions: dict[str, ConversationSession] = {}
        self._lock = Lock()

    def free_response(self, query: str) -> dict:
        return {
            "message": self._local_response(query),
            "response_id": None,
            "payment_prompt": "Continuar por 1€",
        }

    def start_paid_session(self, original_query: str) -> dict:
        message, response_id = self._paid_response(
            (
                "Continua esta conversa nao urgente em portugues de Portugal. "
                "Mantem um tom austero e util. Estrutura sempre em tres blocos: "
                "o que esta a acontecer, o que mais pesa, proximo passo simples.\n\n"
                f"Contexto inicial: {compact_text(original_query)}"
            )
        )

        session = ConversationSession(id=str(uuid.uuid4()), original_query=original_query, previous_response_id=response_id)
        with self._lock:
            self._sessions[session.id] = session
        return {"session_id": session.id, "message": message, "response_id": response_id}

    def continue_session(self, session_id: str, user_message: str) -> dict:
        with self._lock:
            session = self._sessions.get(session_id)
        if not session:
            raise ValueError("Sessao nao encontrada.")

        message, response_id = self._paid_response(
            compact_text(user_message),
            previous_response_id=session.previous_response_id,
        )
        with self._lock:
            session.previous_response_id = response_id or session.previous_response_id
        return {"message": message, "response_id": response_id}

    def _paid_response(self, user_message: str, previous_response_id: str | None = None) -> tuple[str, str | None]:
        if not self.settings.openai_api_key:
            return self._local_response(user_message), None

        instructions = self._load_prompt()
        payload = {
            "model": self.settings.openai_model,
            "instructions": instructions,
            "input": [
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": compact_text(user_message)}],
                }
            ],
        }
        if previous_response_id:
            payload["previous_response_id"] = previous_response_id

        request = Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=90) as response:
                response_json = json.loads(response.read().decode("utf-8"))
            message = self._extract_text(response_json)
            if not message:
                raise RuntimeError("A resposta nao trouxe texto utilizavel.")
            return message, response_json.get("id")
        except (HTTPError, URLError, RuntimeError):
            return self._local_response(user_message), None

    def _load_prompt(self) -> str:
        if self.settings.prompt_file.exists():
            return self.settings.prompt_file.read_text(encoding="utf-8").strip()
        return (
            "Falas em portugues de Portugal. "
            "Nao diagnosticas nem fazes aconselhamento clinico. "
            "Responde no maximo em 6 linhas com os blocos "
            "'O que esta a acontecer', 'O que mais pesa' e 'Proximo passo simples'."
        )

    def _extract_text(self, response_json: dict) -> str:
        output_text = response_json.get("output_text")
        if output_text:
            return output_text.strip()

        chunks: list[str] = []
        for item in response_json.get("output", []):
            for content in item.get("content", []):
                text_value = content.get("text")
                if isinstance(text_value, str):
                    chunks.append(text_value)
                elif isinstance(text_value, dict) and text_value.get("value"):
                    chunks.append(text_value["value"])
        return "\n".join(chunk.strip() for chunk in chunks if chunk.strip())

    def _local_response(self, query: str) -> str:
        clean_query = compact_text(query)
        lowered = clean_query.lower()

        if any(term in lowered for term in ("decidir", "escolher", "indeciso", "indecisa")):
            weight = "A decisao esta parada porque ainda falta um criterio claro."
            next_step = "Escreva as duas opcoes e escolha apenas o que precisa de proteger hoje."
        elif any(term in lowered for term in ("discussao", "discussão", "zanga", "casa")):
            weight = "O conflito esta a ocupar espaco mental e a empurrar a resposta."
            next_step = "Adie a conversa final e anote em uma frase o ponto que precisa mesmo de resolver."
        elif any(term in lowered for term in ("ansiedade", "stress", "panico", "pânico", "nao consigo desligar", "não consigo desligar")):
            weight = "O excesso de pensamentos esta a misturar o urgente com o acessorio."
            next_step = "Escolha uma unica tarefa para as proximas duas horas e deixe o resto fora dessa janela."
        elif any(term in lowered for term in ("dormir", "sono", "insónia", "insonia")):
            weight = "Ha cansaco acumulado e pouca margem para decidir bem agora."
            next_step = "Suspenda decisoes maiores hoje e deixe preparado apenas o primeiro passo de amanha."
        else:
            weight = "O tema ficou difuso e isso aumenta o bloqueio."
            next_step = "Reduza isto a uma frase e escolha apenas o passo que pode mesmo fazer hoje."

        return (
            "Vamos organizar isto.\n"
            f"O que esta a acontecer: {clean_query[:180]}.\n"
            f"O que mais pesa: {weight}\n"
            f"Proximo passo simples: {next_step}"
        )
