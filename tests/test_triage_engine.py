import unittest

from core.triage_engine import TriageEngine


class TriageEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = TriageEngine()

    def assert_triage(self, query: str, expected: str) -> None:
        result = self.engine.classify(query)
        self.assertEqual(result.triage_class, expected, query)

    def test_emergency_queries(self) -> None:
        cases = [
            "dor no peito",
            "nao consigo respirar",
            "desmaiei agora",
            "sangramento intenso",
            "tive uma convulsao",
            "acho que e um avc",
            "houve overdose",
            "quero morrer",
        ]
        for case in cases:
            with self.subTest(case=case):
                self.assert_triage(case, "emergency_potential")

    def test_urgent_queries(self) -> None:
        cases = [
            "febre alta no meu filho",
            "crise de ansiedade",
            "ataque de panico",
            "crianca doente",
            "tensao alta",
            "vómitos persistentes",
        ]
        for case in cases:
            with self.subTest(case=case):
                self.assert_triage(case, "urgent_care")

    def test_practical_queries(self) -> None:
        cases = [
            "farmacia aberta",
            "preciso de um medicamento",
            "hospital mais proximo",
            "onde ir para urgencia",
            "telefone de um hospital",
        ]
        for case in cases:
            with self.subTest(case=case):
                self.assert_triage(case, "practical_health")

    def test_conversation_queries(self) -> None:
        cases = [
            "nao sei o que fazer",
            "tive uma discussao em casa",
            "estou confuso com isto",
            "nao consigo desligar a cabeca",
        ]
        for case in cases:
            with self.subTest(case=case):
                self.assert_triage(case, "light_conversation")


if __name__ == "__main__":
    unittest.main()
