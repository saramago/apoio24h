import json
import threading
import time
import unittest
from dataclasses import replace
from urllib.request import Request, urlopen

from core.config import get_settings
from server import create_server


class ServerIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        settings = replace(
            get_settings(),
            openai_api_key="",
            admin_token="test-admin",
            mbway_mode="mock",
            mbway_sandbox_delay_seconds=0.01,
            enable_provider_refresh_jobs=False,
        )
        cls.server, cls.app = create_server(host="127.0.0.1", port=0, settings=settings)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.05)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def request_json(self, path: str, payload: dict | None = None) -> tuple[int, dict]:
        method = "POST" if payload is not None else "GET"
        request = Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps(payload).encode("utf-8") if payload is not None else None,
            headers={"Content-Type": "application/json"},
            method=method,
        )
        with urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_healthz(self) -> None:
        status, payload = self.request_json("/healthz")
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ok")

    def test_emergency_triage(self) -> None:
        status, payload = self.request_json("/api/triage", {"query": "dor no peito"})
        self.assertEqual(status, 200)
        self.assertEqual(payload["triage"]["triage_class"], "emergency_potential")

    def test_light_conversation_flow(self) -> None:
        status, payload = self.request_json("/api/triage", {"query": "nao sei o que fazer"})
        self.assertEqual(status, 200)
        self.assertEqual(payload["triage"]["triage_class"], "light_conversation")
        self.assertIn("free_response", payload)

        _, checkin = self.request_json("/api/checkin", {"plan": "continue_1", "customer_phone": "919999999"})
        time.sleep(0.03)
        _, checkin_status = self.request_json(f"/api/checkin/status?id={checkin['checkin_id']}")
        self.assertEqual(checkin_status["status_code"], "AUTHORIZED")

        _, session = self.request_json(
            "/api/session/start",
            {
                "plan": "continue_1",
                "checkin_id": checkin["checkin_id"],
                "original_query": "nao sei o que fazer",
            },
        )
        self.assertIn("session_id", session)

        _, chat = self.request_json("/api/chat", {"session_id": session["session_id"], "message": "Isto continua a pesar."})
        self.assertIn("message", chat)

    def test_session_memory_links_follow_up_query(self) -> None:
        session_id = "sessao-teste"
        _, first = self.request_json("/api/triage", {"query": "preciso de um medicamento", "session_id": session_id})
        self.assertEqual(first["triage"]["triage_class"], "practical_health")

        _, second = self.request_json("/api/triage", {"query": "em lisboa", "session_id": session_id})
        self.assertEqual(second["triage"]["triage_class"], "practical_health")
        self.assertTrue(second["memory"]["continued"])
        self.assertIn("medicamento", second["memory"]["resolved_query"])

    def test_admin_status(self) -> None:
        status, payload = self.request_json("/api/admin/status?token=test-admin")
        self.assertEqual(status, 200)
        self.assertIn("providers", payload)


if __name__ == "__main__":
    unittest.main()
