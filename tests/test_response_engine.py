import unittest

from core.conversation_engine import ConversationEngine
from core.config import get_settings
from core.response_engine import ResponseEngine
from core.resource_engine import ResourceEngine
from core.providers import build_provider_registry
from core.triage_engine import TriageEngine


class ResponseEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        providers = build_provider_registry()
        for provider in providers.values():
            provider.get_data(force_refresh=True)
        self.triage_engine = TriageEngine()
        self.resource_engine = ResourceEngine(providers)
        self.response_engine = ResponseEngine(ConversationEngine(get_settings()))

    def build_response(self, query: str):
        triage = self.triage_engine.classify(query)
        resources = self.resource_engine.build(triage, query)
        return self.response_engine.build(triage, query, {}, resources)

    def test_emergency_response_is_immediate(self) -> None:
        response = self.build_response("dor no peito")
        self.assertEqual(response.title, "Pode ser uma emergencia")
        self.assertIn("Ligue 112 agora.", response.message)
        self.assertLessEqual(len(response.message.splitlines()), 4)
        self.assertEqual(response.actions[0].label, "Ligar 112")

    def test_urgent_response_is_conservative(self) -> None:
        response = self.build_response("febre alta")
        self.assertEqual(response.title, "Precisa de avaliacao rapida")
        self.assertIn("Contacte o SNS 24 ou va a uma urgencia.", response.message)
        self.assertLessEqual(len(response.actions), 2)

    def test_practical_response_starts_with_action(self) -> None:
        response = self.build_response("preciso de medicamento")
        self.assertEqual(response.title, "Para procurar medicamento")
        self.assertIn("Comece por: Pesquisar medicamento.", response.message)
        self.assertLessEqual(len(response.actions), 2)
        self.assertEqual(response.actions[0].label, "Pesquisar medicamento")

    def test_conversation_response_is_structured(self) -> None:
        response = self.build_response("nao sei o que fazer")
        self.assertEqual(response.title, "Vamos organizar isto")
        self.assertIn("Vamos organizar isto.", response.message)
        self.assertIn("O que esta a acontecer:", response.message)
        self.assertIn("O que mais pesa:", response.message)
        self.assertIn("Proximo passo simples:", response.message)
        self.assertEqual(response.payment_prompt, "Continuar por 1€")


if __name__ == "__main__":
    unittest.main()
