#!/usr/bin/env python3

import json
import os
import time
import uuid
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASE_DIR = Path(__file__).resolve().parent
PROMPT_FILE = BASE_DIR / "prompts" / "advisor_system.txt"


def load_dotenv() -> None:
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


load_dotenv()

DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")
MBWAY_PHONE = os.environ.get("MBWAY_PHONE", "912606050")
MBWAY_MODE = os.environ.get("MBWAY_MODE", "mock").strip().lower()
MBWAY_SANDBOX_DELAY_SECONDS = float(os.environ.get("MBWAY_SANDBOX_DELAY_SECONDS", "3"))
SIBS_CLIENT_ID = os.environ.get("SIBS_CLIENT_ID", "").strip()
SIBS_BEARER_TOKEN = os.environ.get("SIBS_BEARER_TOKEN", "").strip()
SIBS_TERMINAL_ID = os.environ.get("SIBS_TERMINAL_ID", "").strip()
SIBS_CHANNEL = os.environ.get("SIBS_CHANNEL", "web").strip() or "web"
SIBS_BASE_URL = os.environ.get("SIBS_BASE_URL", "https://sandbox.sibspayments.com").strip()
SESSION_PLANS = {
    "5min": {"label": "5 minutos", "amount": 1},
    "30min": {"label": "30 minutos", "amount": 5},
    "60min": {"label": "1 hora", "amount": 49},
}
CHECKINS = {}


def load_system_prompt() -> str:
    if PROMPT_FILE.exists():
        return PROMPT_FILE.read_text(encoding="utf-8").strip()

    return (
        "You are a supportive Portuguese-language emotional support assistant. "
        "Use a calm, empathic tone, avoid diagnosis, and escalate to emergency guidance "
        "when there is risk of self-harm or immediate danger."
    )


def plan_to_text(plan_key: str) -> str:
    plan = SESSION_PLANS.get(plan_key)
    if not plan:
        raise ValueError("Plano de check-in invalido.")

    return (
        "Dados do check-in:\n"
        f"- Plano selecionado: {plan['label']}\n"
        f"- Valor esperado: {plan['amount']} EUR\n"
        "- O site nao recebeu automaticamente o numero do cliente nem a confirmacao final do pagamento.\n"
        "Faz um acolhimento inicial generico, claro e breve."
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


def format_customer_phone(phone: str) -> str:
    digits = "".join(char for char in phone if char.isdigit())
    if not digits:
        raise ValueError("Indique um numero de telemovel valido.")
    if digits.startswith("351") and len(digits) >= 12:
        national = digits[3:]
    elif len(digits) == 9:
        national = digits
    else:
        raise ValueError("O numero MB WAY deve ter 9 digitos ou incluir o prefixo 351.")
    return f"351#{national}"


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


def sibs_request(path: str, method: str = "GET", payload: dict | None = None, authorization: str | None = None) -> dict:
    if not SIBS_CLIENT_ID:
        raise RuntimeError("Defina SIBS_CLIENT_ID para usar a sandbox real da SIBS.")
    if not authorization:
        raise RuntimeError("Falta o header Authorization para a chamada SIBS.")

    headers = {
        "X-IBM-Client-Id": SIBS_CLIENT_ID,
        "Authorization": authorization,
        "Content-Type": "application/json",
    }
    request = Request(
        f"{SIBS_BASE_URL}{path}",
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers=headers,
        method=method,
    )

    try:
        with urlopen(request, timeout=90) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"SIBS devolveu erro HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Nao foi possivel contactar a SIBS: {exc.reason}") from exc


def create_sibs_checkout(plan_key: str) -> dict:
    if not SIBS_BEARER_TOKEN:
        raise RuntimeError("Defina SIBS_BEARER_TOKEN para usar a sandbox real da SIBS.")
    if not SIBS_TERMINAL_ID:
        raise RuntimeError("Defina SIBS_TERMINAL_ID para usar a sandbox real da SIBS.")

    plan = SESSION_PLANS[plan_key]
    now = datetime.now(timezone.utc)
    merchant_transaction_id = f"apoio24h-{uuid.uuid4().hex[:20]}"
    payload = {
        "merchant": {
            "terminalId": int(SIBS_TERMINAL_ID),
            "channel": SIBS_CHANNEL,
            "merchantTransactionId": merchant_transaction_id,
        },
        "transaction": {
            "transactionTimestamp": now.isoformat().replace("+00:00", "Z"),
            "description": f"Check-in Apoio24h {plan['label']}",
            "moto": False,
            "paymentType": "PURS",
            "amount": {
                "value": plan["amount"],
                "currency": "EUR",
            },
            "paymentMethod": ["MBWAY"],
        },
    }

    return sibs_request(
        "/sibs/spg/v2/payments",
        method="POST",
        payload=payload,
        authorization=f"Bearer {SIBS_BEARER_TOKEN}",
    )


def create_sibs_mbway_purchase(transaction_id: str, transaction_signature: str, customer_phone: str) -> dict:
    payload = {
        "customerPhone": format_customer_phone(customer_phone),
    }
    return sibs_request(
        f"/sibs/spg/v2/payments/{transaction_id}/mbway-id/purchase",
        method="POST",
        payload=payload,
        authorization=f"Digest {transaction_signature}",
    )


def get_sibs_payment_status(transaction_id: str) -> dict:
    if not SIBS_BEARER_TOKEN:
        raise RuntimeError("Defina SIBS_BEARER_TOKEN para consultar o estado na SIBS.")
    return sibs_request(
        f"/sibs/spg/v2/payments/{transaction_id}/status",
        method="GET",
        authorization=f"Bearer {SIBS_BEARER_TOKEN}",
    )


class AppHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def do_GET(self):
        if self.path.startswith("/api/checkin/status"):
            try:
                checkin_id = self._parse_checkin_id()
                checkin = CHECKINS.get(checkin_id)
                if not checkin:
                    raise ValueError("Check-in nao encontrado.")
                self._send_json(HTTPStatus.OK, self._serialize_checkin(checkin))
            except Exception as exc:  # noqa: BLE001
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return

        super().do_GET()

    def do_POST(self):
        if self.path not in {"/api/checkin", "/api/session/start", "/api/chat"}:
            self.send_error(HTTPStatus.NOT_FOUND, "Endpoint nao encontrado.")
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length).decode("utf-8")
            data = json.loads(raw_body or "{}")

            if self.path == "/api/checkin":
                response_payload = self._build_checkin_payload(data)
                self._send_json(HTTPStatus.OK, response_payload)
                return
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

    def _build_checkin_payload(self, data: dict) -> dict:
        plan_key = (data.get("plan") or "").strip()
        plan = SESSION_PLANS.get(plan_key)
        if not plan:
            raise ValueError("Plano de check-in invalido.")
        customer_phone = (data.get("customer_phone") or "").strip()
        formatted_phone = format_customer_phone(customer_phone)

        checkin_id = str(uuid.uuid4())
        created_at = time.time()
        checkin = {
            "id": checkin_id,
            "plan_key": plan_key,
            "amount": plan["amount"],
            "label": plan["label"],
            "customer_phone": formatted_phone,
            "created_at": created_at,
            "authorized_at": created_at + MBWAY_SANDBOX_DELAY_SECONDS,
            "status_code": "PENDING",
            "transaction_id": None,
            "transaction_signature": None,
            "merchant_transaction_id": None,
        }

        payload = self._serialize_checkin(checkin)
        payload["checkin_id"] = checkin_id

        if MBWAY_MODE == "deeplink":
            CHECKINS[checkin_id] = checkin
            payload["payment_url"] = f"mbway://send?phone={MBWAY_PHONE}&amount={plan['amount']}"
            payload["payment_note"] = (
                "Foi aberto o pedido MB WAY no dispositivo. O site aguarda a autorizacao."
            )
        elif MBWAY_MODE == "sibs_sandbox":
            checkout = create_sibs_checkout(plan_key)
            transaction_id = checkout.get("transactionID")
            transaction_signature = checkout.get("transactionSignature")
            merchant = checkout.get("merchant") or {}
            if not transaction_id or not transaction_signature:
                raise RuntimeError("A SIBS nao devolveu transactionID/transactionSignature no checkout.")
            purchase = create_sibs_mbway_purchase(transaction_id, transaction_signature, customer_phone)
            checkin["transaction_id"] = transaction_id
            checkin["transaction_signature"] = transaction_signature
            checkin["merchant_transaction_id"] = merchant.get("merchantTransactionId")
            checkin["status_code"] = purchase.get("paymentStatus") or "PENDING"
            CHECKINS[checkin_id] = checkin
            payload = self._serialize_checkin(checkin)
            payload["checkin_id"] = checkin_id
            payload["payment_note"] = (
                "Pedido MB WAY enviado pela sandbox SIBS. O sistema vai validar o estado automaticamente."
            )
        else:
            CHECKINS[checkin_id] = checkin
            payload["payment_note"] = (
                "Sandbox ativa: o pagamento de teste sera autorizado automaticamente em poucos segundos."
            )

        return payload

    def _serialize_checkin(self, checkin: dict) -> dict:
        status_code = self._current_checkin_status(checkin)
        label = checkin["label"]
        if status_code in {"AUTHORIZED", "Success"}:
            status = f"Pagamento MB WAY autorizado para o check-in de {label}."
        else:
            status = f"A aguardar autorizacao MB WAY para o check-in de {label}."

        return {
            "status_code": status_code,
            "status": status,
            "payment_note": "",
        }

    def _build_start_payload(self, data: dict) -> dict:
        plan_key = (data.get("plan") or "").strip()
        if plan_key not in SESSION_PLANS:
            raise ValueError("Escolha primeiro um check-in valido.")
        checkin_id = (data.get("checkin_id") or "").strip()
        checkin = CHECKINS.get(checkin_id)
        if not checkin:
            raise ValueError("Check-in nao encontrado.")
        if checkin["plan_key"] != plan_key:
            raise ValueError("O check-in nao corresponde ao plano selecionado.")
        if self._current_checkin_status(checkin) not in {"AUTHORIZED", "Success"}:
            raise ValueError("O pagamento ainda nao foi autorizado.")

        initial_message = (
            "Inicia a sessao em portugues de Portugal. "
            "Faz acolhimento inicial, reconhece o check-in escolhido e coloca uma primeira pergunta util."
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
                            "text": f"{plan_to_text(plan_key)}\n\nPedido inicial:\n{initial_message}",
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
            plan_key = (data.get("plan") or "").strip()
            payload["input"].insert(
                0,
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": plan_to_text(plan_key)}
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

    def _current_checkin_status(self, checkin: dict) -> str:
        if MBWAY_MODE == "mock" and time.time() >= checkin["authorized_at"]:
            checkin["status_code"] = "AUTHORIZED"
        elif MBWAY_MODE == "sibs_sandbox" and checkin.get("transaction_id"):
            status_response = get_sibs_payment_status(checkin["transaction_id"])
            checkin["status_code"] = status_response.get("paymentStatus") or checkin["status_code"]
        return checkin["status_code"]

    def _parse_checkin_id(self) -> str:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        checkin_ids = params.get("id") or []
        if checkin_ids:
            return checkin_ids[0]
        raise ValueError("Falta o identificador do check-in.")


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
