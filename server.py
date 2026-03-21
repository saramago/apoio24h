#!/usr/bin/env python3

import json
import os
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASE_DIR = Path(__file__).resolve().parent
PROMPT_FILE = BASE_DIR / "prompts" / "advisor_system.txt"
DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")


def load_system_prompt() -> str:
    if PROMPT_FILE.exists():
        return PROMPT_FILE.read_text(encoding="utf-8").strip()

    return (
        "You are a supportive Portuguese-language emotional support assistant. "
        "Use a calm, empathic tone, avoid diagnosis, and escalate to emergency guidance "
        "when there is risk of self-harm or immediate danger."
    )


def onboarding_to_text(onboarding: dict) -> str:
    return (
        "Dados do onboarding:\n"
        f"- Primeiro nome: {onboarding.get('firstName', '').strip()}\n"
        f"- Nome preferido: {onboarding.get('preferredName', '').strip() or 'Nao indicado'}\n"
        f"- Faixa etaria: {onboarding.get('ageRange', '').strip()}\n"
        f"- Intensidade emocional: {onboarding.get('distressLevel', '').strip()}\n"
        f"- Motivo principal: {onboarding.get('reason', '').strip()}\n"
        f"- Objetivo da conversa: {onboarding.get('goal', '').strip()}\n"
        "Usa estes dados para acolhimento inicial, mas sem inventar informacao adicional."
    )


def extract_text(response_json: dict) -> str:
    output_text = response_json.get("output_text")
    if output_text:
        return output_text.strip()

    chunks = []
    for item in response_json.get("output", []):
        for content in item.get("content", []):
            text_value = content.get("text")
            if isinstance(text_value, str):
                chunks.append(text_value)
            elif isinstance(text_value, dict) and text_value.get("value"):
                chunks.append(text_value["value"])
    return "\n".join(chunk.strip() for chunk in chunks if chunk.strip())


def call_openai(payload: dict) -> dict:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Defina a variavel OPENAI_API_KEY antes de iniciar o servidor.")

    request = Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=90) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI devolveu erro HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Nao foi possivel contactar a OpenAI: {exc.reason}") from exc


class AppHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def do_POST(self):
        if self.path not in {"/api/session/start", "/api/chat"}:
            self.send_error(HTTPStatus.NOT_FOUND, "Endpoint nao encontrado.")
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length).decode("utf-8")
            data = json.loads(raw_body or "{}")

            if self.path == "/api/session/start":
                payload = self._build_start_payload(data)
            else:
                payload = self._build_chat_payload(data)

            response_json = call_openai(payload)
            message = extract_text(response_json)
            if not message:
                raise RuntimeError("A resposta da OpenAI nao trouxe texto utilizavel.")

            self._send_json(
                HTTPStatus.OK,
                {"message": message, "response_id": response_json.get("id")},
            )
        except Exception as exc:  # noqa: BLE001
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    def _build_start_payload(self, data: dict) -> dict:
        onboarding = data.get("onboarding") or {}
        first_name = onboarding.get("firstName", "").strip()
        reason = onboarding.get("reason", "").strip()
        goal = onboarding.get("goal", "").strip()

        if not first_name or not reason or not goal:
            raise ValueError("O onboarding precisa de nome, motivo e objetivo.")

        initial_message = (
            "Inicia a sessao em portugues de Portugal. "
            "Cumprimenta a pessoa pelo nome, faz acolhimento inicial e coloca uma primeira pergunta util."
        )

        return {
            "model": DEFAULT_MODEL,
            "instructions": load_system_prompt(),
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": f"{onboarding_to_text(onboarding)}\n\nPedido inicial:\n{initial_message}",
                        }
                    ],
                }
            ],
        }

    def _build_chat_payload(self, data: dict) -> dict:
        user_message = (data.get("message") or "").strip()
        if not user_message:
            raise ValueError("A mensagem nao pode estar vazia.")

        payload = {
            "model": DEFAULT_MODEL,
            "instructions": load_system_prompt(),
            "input": [
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": user_message}],
                }
            ],
        }

        previous_response_id = data.get("previous_response_id")
        if previous_response_id:
            payload["previous_response_id"] = previous_response_id
        else:
            onboarding = data.get("onboarding") or {}
            payload["input"].insert(
                0,
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": onboarding_to_text(onboarding)}
                    ],
                },
            )

        return payload

    def _send_json(self, status: HTTPStatus, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run():
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), AppHandler)
    print(f"A servir em http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor terminado.")
    finally:
        server.server_close()


if __name__ == "__main__":
    run()
