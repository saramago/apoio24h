import time
import unittest
from dataclasses import replace

from core.config import get_settings
from core.payments_engine import PaymentManager


class PaymentManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        settings = replace(
            get_settings(),
            mbway_mode="mock",
            mbway_sandbox_delay_seconds=0.01,
        )
        self.manager = PaymentManager(settings)

    def test_mock_payment_authorizes_after_delay(self) -> None:
        payload = self.manager.create_checkin("continue_1", "919999999")
        self.assertEqual(payload["status_code"], "PENDING")
        time.sleep(0.03)
        status = self.manager.get_status(payload["checkin_id"])
        self.assertEqual(status["status_code"], "AUTHORIZED")


if __name__ == "__main__":
    unittest.main()
