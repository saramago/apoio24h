from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from core.config import Settings


PRODUCTS = {
    "continue_1": {"label": "Continuar", "amount": 1},
    "session_3": {"label": "Sessao alargada", "amount": 3},
}


@dataclass
class Checkin:
    id: str
    plan_key: str
    amount: int
    label: str
    customer_phone: str
    created_at: float
    authorized_at: float
    status_code: str
    transaction_id: str | None = None
    transaction_signature: str | None = None


class PaymentManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._checkins: dict[str, Checkin] = {}
        self._lock = Lock()

    def create_checkin(self, plan_key: str, customer_phone: str) -> dict:
        plan = PRODUCTS.get(plan_key)
        if not plan:
            raise ValueError("Produto invalido.")
        formatted_phone = self._format_customer_phone(customer_phone)

        checkin = Checkin(
            id=str(uuid.uuid4()),
            plan_key=plan_key,
            amount=plan["amount"],
            label=plan["label"],
            customer_phone=formatted_phone,
            created_at=time.time(),
            authorized_at=time.time() + self.settings.mbway_sandbox_delay_seconds,
            status_code="PENDING",
        )

        payload = self._serialize(checkin)
        payload["checkin_id"] = checkin.id

        if self.settings.mbway_mode == "deeplink":
            with self._lock:
                self._checkins[checkin.id] = checkin
            payload["payment_url"] = f"mbway://send?phone={self.settings.mbway_phone}&amount={plan['amount']}"
            payload["payment_note"] = "Foi aberto o pedido MB WAY no dispositivo. O site aguarda a autorizacao."
            return payload

        if self.settings.mbway_mode == "sibs_sandbox":
            checkout = self._create_sibs_checkout(plan_key)
            transaction_id = checkout.get("transactionID")
            transaction_signature = checkout.get("transactionSignature")
            if not transaction_id or not transaction_signature:
                raise RuntimeError("A SIBS nao devolveu transactionID/transactionSignature.")
            purchase = self._create_sibs_mbway_purchase(transaction_id, transaction_signature, customer_phone)
            checkin.transaction_id = transaction_id
            checkin.transaction_signature = transaction_signature
            checkin.status_code = purchase.get("paymentStatus") or "PENDING"
            with self._lock:
                self._checkins[checkin.id] = checkin
            payload = self._serialize(checkin)
            payload["checkin_id"] = checkin.id
            payload["payment_note"] = "Pedido MB WAY enviado. O sistema vai validar o estado automaticamente."
            return payload

        with self._lock:
            self._checkins[checkin.id] = checkin
        payload["payment_note"] = "Sandbox ativa: o pagamento de teste sera autorizado automaticamente em poucos segundos."
        return payload

    def get_status(self, checkin_id: str) -> dict:
        with self._lock:
            checkin = self._checkins.get(checkin_id)
        if not checkin:
            raise ValueError("Pedido nao encontrado.")
        return self._serialize(checkin)

    def is_authorized(self, checkin_id: str, plan_key: str) -> bool:
        with self._lock:
            checkin = self._checkins.get(checkin_id)
        if not checkin:
            raise ValueError("Pedido nao encontrado.")
        if checkin.plan_key != plan_key:
            raise ValueError("O pedido nao corresponde ao produto selecionado.")
        return self._current_status(checkin) in {"AUTHORIZED", "Success"}

    def _serialize(self, checkin: Checkin) -> dict:
        status_code = self._current_status(checkin)
        status = "Pagamento autorizado." if status_code in {"AUTHORIZED", "Success"} else "A aguardar autorizacao MB WAY."
        return {
            "status_code": status_code,
            "status": status,
            "payment_note": "",
        }

    def _current_status(self, checkin: Checkin) -> str:
        if self.settings.mbway_mode == "mock" and time.time() >= checkin.authorized_at:
            checkin.status_code = "AUTHORIZED"
        elif self.settings.mbway_mode == "sibs_sandbox" and checkin.transaction_id:
            status_response = self._sibs_request(
                f"/sibs/spg/v2/payments/{checkin.transaction_id}/status",
                method="GET",
                authorization=f"Bearer {self.settings.sibs_bearer_token}",
            )
            checkin.status_code = status_response.get("paymentStatus") or checkin.status_code
        return checkin.status_code

    def _format_customer_phone(self, phone: str) -> str:
        digits = "".join(char for char in phone if char.isdigit())
        if digits.startswith("351") and len(digits) >= 12:
            national = digits[3:]
        elif len(digits) == 9:
            national = digits
        else:
            raise ValueError("Indique um numero de telemovel MB WAY valido.")
        return f"351#{national}"

    def _create_sibs_checkout(self, plan_key: str) -> dict:
        if not self.settings.sibs_client_id or not self.settings.sibs_bearer_token or not self.settings.sibs_terminal_id:
            raise RuntimeError("Credenciais SIBS incompletas.")
        plan = PRODUCTS[plan_key]
        payload = {
            "merchant": {
                "terminalId": int(self.settings.sibs_terminal_id),
                "channel": self.settings.sibs_channel,
                "merchantTransactionId": f"apoio24h-{uuid.uuid4().hex[:20]}",
            },
            "transaction": {
                "transactionTimestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "description": f"Apoio24h {plan['label']}",
                "moto": False,
                "paymentType": "PURS",
                "amount": {"value": plan["amount"], "currency": "EUR"},
                "paymentMethod": ["MBWAY"],
            },
        }
        return self._sibs_request(
            "/sibs/spg/v2/payments",
            method="POST",
            payload=payload,
            authorization=f"Bearer {self.settings.sibs_bearer_token}",
        )

    def _create_sibs_mbway_purchase(self, transaction_id: str, transaction_signature: str, customer_phone: str) -> dict:
        payload = {"customerPhone": self._format_customer_phone(customer_phone)}
        return self._sibs_request(
            f"/sibs/spg/v2/payments/{transaction_id}/mbway-id/purchase",
            method="POST",
            payload=payload,
            authorization=f"Digest {transaction_signature}",
        )

    def _sibs_request(self, path: str, method: str, authorization: str, payload: dict | None = None) -> dict:
        request = Request(
            f"{self.settings.sibs_base_url}{path}",
            data=json.dumps(payload).encode("utf-8") if payload is not None else None,
            headers={
                "X-IBM-Client-Id": self.settings.sibs_client_id,
                "Authorization": authorization,
                "Content-Type": "application/json",
            },
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
