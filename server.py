#!/usr/bin/env python3

from __future__ import annotations

import json
import os
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from core.config import Settings, get_settings
from core.conversation_engine import ConversationEngine
from core.jobs import ProviderRefreshJobs
from core.observability import Observability
from core.payments_engine import PRODUCTS, PaymentManager
from core.providers import build_provider_registry
from core.response_engine import ResponseEngine
from core.resource_engine import ResourceEngine
from core.session_memory import SessionMemoryStore
from core.triage_engine import TriageEngine


class AppContext:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.observability = Observability()
        self.providers = build_provider_registry()
        self.triage_engine = TriageEngine()
        self.resource_engine = ResourceEngine(self.providers)
        self.conversation_engine = ConversationEngine(settings)
        self.response_engine = ResponseEngine(self.conversation_engine)
        self.payments = PaymentManager(settings)
        self.session_memory = SessionMemoryStore(settings.session_memory_ttl_seconds)
        self.jobs = ProviderRefreshJobs(self.providers, settings.provider_refresh_interval_seconds)
        self.jobs.warmup()

    def provider_health(self) -> list[dict]:
        return [provider.health_check().to_dict() for provider in self.providers.values()]


def build_app(settings: Settings | None = None) -> AppContext:
    return AppContext(settings or get_settings())


def make_handler(app: AppContext):
    class AppHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(app.settings.base_dir), **kwargs)

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == "/healthz":
                self._send_json(
                    HTTPStatus.OK,
                    {"status": "ok", "providers": app.provider_health()},
                )
                return

            if parsed.path == "/api/checkin/status":
                try:
                    checkin_id = self._require_query_value(parsed, "id")
                    payload = app.payments.get_status(checkin_id)
                    self._send_json(HTTPStatus.OK, payload)
                except Exception as exc:  # noqa: BLE001
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            if parsed.path == "/api/admin/status":
                try:
                    self._require_admin(parsed)
                    snapshot = app.observability.snapshot(app.provider_health())
                    self._send_json(HTTPStatus.OK, snapshot)
                except Exception as exc:  # noqa: BLE001
                    self._send_json(HTTPStatus.UNAUTHORIZED, {"error": str(exc)})
                return

            if parsed.path == "/admin":
                try:
                    self._require_admin(parsed)
                    self._send_html(HTTPStatus.OK, render_admin_page(app))
                except Exception as exc:  # noqa: BLE001
                    self._send_html(HTTPStatus.UNAUTHORIZED, f"<h1>Acesso negado</h1><p>{str(exc)}</p>")
                return

            super().do_GET()

        def do_POST(self):
            parsed = urlparse(self.path)
            if parsed.path not in {"/api/triage", "/api/checkin", "/api/session/start", "/api/chat"}:
                self.send_error(HTTPStatus.NOT_FOUND, "Endpoint nao encontrado.")
                return

            try:
                data = self._read_json_body()
                if parsed.path == "/api/triage":
                    payload = self._handle_triage(data)
                elif parsed.path == "/api/checkin":
                    payload = self._handle_checkin(data)
                elif parsed.path == "/api/session/start":
                    payload = self._handle_session_start(data)
                else:
                    payload = self._handle_chat(data)
                self._send_json(HTTPStatus.OK, payload)
            except Exception as exc:  # noqa: BLE001
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

        def _handle_triage(self, data: dict) -> dict:
            query = (data.get("query") or "").strip()
            location = data.get("location") or None
            session_id = app.session_memory.ensure_session_id(data.get("session_id"))
            resolved_query, memory_context = app.session_memory.resolve_query(session_id, query)

            app.observability.record_event("submitted_query")
            app.observability.record_query(resolved_query)

            triage = app.triage_engine.classify(resolved_query)
            app.observability.record_event(f"triage_{triage.triage_class}")
            app.session_memory.remember(session_id, query, triage.triage_class, resolved_query)

            resources = app.resource_engine.build(triage, resolved_query, location)
            response = app.response_engine.build(triage, resolved_query, memory_context, resources)
            payload = {
                "triage": triage.to_dict(),
                "response": response.to_dict(),
                "resources": resources,
                "products": {"continue_1": PRODUCTS["continue_1"]},
                "memory": {
                    **memory_context,
                    "session_id": session_id,
                    "triage_class": triage.triage_class,
                    "resolved_query": resolved_query,
                },
            }

            if triage.triage_class == "light_conversation":
                app.observability.record_event("free_response_shown")
                payload["free_response"] = app.conversation_engine.free_response(resolved_query)

            return payload

        def _handle_checkin(self, data: dict) -> dict:
            plan_key = (data.get("plan") or "").strip()
            customer_phone = (data.get("customer_phone") or "").strip()
            payload = app.payments.create_checkin(plan_key, customer_phone)
            app.observability.record_event("payment_started")
            return payload

        def _handle_session_start(self, data: dict) -> dict:
            plan_key = (data.get("plan") or "").strip()
            checkin_id = (data.get("checkin_id") or "").strip()
            original_query = (data.get("original_query") or "").strip()
            if not original_query:
                raise ValueError("Falta o texto inicial da conversa.")
            if not app.payments.is_authorized(checkin_id, plan_key):
                raise ValueError("O pagamento ainda nao foi autorizado.")

            session_payload = app.conversation_engine.start_paid_session(original_query)
            app.observability.record_event("payment_success")
            return session_payload

        def _handle_chat(self, data: dict) -> dict:
            session_id = (data.get("session_id") or "").strip()
            message = (data.get("message") or "").strip()
            if not message:
                raise ValueError("A mensagem nao pode ficar vazia.")
            payload = app.conversation_engine.continue_session(session_id, message)
            return payload

        def _read_json_body(self) -> dict:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length).decode("utf-8")
            return json.loads(raw_body or "{}")

        def _send_json(self, status: HTTPStatus, payload: dict):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_html(self, status: HTTPStatus, html: str):
            body = html.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _require_query_value(self, parsed, key: str) -> str:
            values = parse_qs(parsed.query).get(key) or []
            if not values:
                raise ValueError(f"Falta o parametro {key}.")
            return values[0]

        def _require_admin(self, parsed) -> None:
            if not app.settings.admin_token:
                raise PermissionError("Painel admin indisponivel.")
            token = self._require_query_value(parsed, "token")
            if token != app.settings.admin_token:
                raise PermissionError("Token admin invalido.")

    return AppHandler


def render_admin_page(app: AppContext) -> str:
    snapshot = app.observability.snapshot(app.provider_health())
    rows = []
    for provider in snapshot["providers"]:
        rows.append(
            "<tr>"
            f"<td>{provider['name']}</td>"
            f"<td>{provider['status']}</td>"
            f"<td>{provider['mode']}</td>"
            f"<td>{provider['validated']}</td>"
            f"<td>{provider['last_sync_at'] or '-'}</td>"
            f"<td>{provider['last_error'] or '-'}</td>"
            "</tr>"
        )

    event_rows = "".join(f"<li>{name}: {count}</li>" for name, count in snapshot["events"].items()) or "<li>Sem eventos.</li>"
    query_rows = "".join(
        f"<li>{entry['query']} ({entry['count']})</li>" for entry in snapshot["top_queries"]
    ) or "<li>Sem queries.</li>"

    return f"""<!DOCTYPE html>
<html lang="pt">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>apoio24h.com admin</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 0; background: #fff; color: #111; }}
    main {{ max-width: 1080px; margin: 0 auto; padding: 32px 20px 56px; }}
    h1, h2 {{ margin: 0 0 16px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 16px; }}
    th, td {{ text-align: left; padding: 10px 12px; border-bottom: 1px solid #ddd; vertical-align: top; }}
    section {{ margin-top: 32px; }}
    ul {{ margin: 0; padding-left: 20px; }}
  </style>
</head>
<body>
  <main>
    <h1>apoio24h.com admin</h1>
    <p>Gerado em {snapshot['generated_at']}</p>
    <section>
      <h2>Providers</h2>
      <table>
        <thead><tr><th>Provider</th><th>Estado</th><th>Modo</th><th>Validado</th><th>Ultima sync</th><th>Ultimo erro</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </section>
    <section>
      <h2>Eventos</h2>
      <ul>{event_rows}</ul>
    </section>
    <section>
      <h2>Queries mais frequentes</h2>
      <ul>{query_rows}</ul>
    </section>
  </main>
</body>
</html>"""


def create_server(
    host: str = "0.0.0.0",
    port: int | None = None,
    settings: Settings | None = None,
) -> tuple[ThreadingHTTPServer, AppContext]:
    active_settings = settings or get_settings()
    app = build_app(active_settings)
    handler_class = make_handler(app)
    listen_port = 8000 if port is None else port
    server = ThreadingHTTPServer((host, listen_port), handler_class)
    return server, app


def run() -> None:
    settings = get_settings()
    port = int(os.environ.get("PORT", "8000"))
    server, app = create_server(host="0.0.0.0", port=port, settings=settings)
    if settings.enable_provider_refresh_jobs:
        app.jobs.start()
    print(f"A servir em http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor terminado.")
    finally:
        app.jobs.stop()
        server.server_close()


if __name__ == "__main__":
    run()
