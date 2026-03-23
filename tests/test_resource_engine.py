import unittest

from core.providers import build_provider_registry
from core.resource_engine import ResourceEngine
from core.types import TriageResult


class ResourceEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.providers = build_provider_registry()
        for provider in self.providers.values():
            provider.get_data(force_refresh=True)
        self.engine = ResourceEngine(self.providers)

    def test_emergency_has_112_action(self) -> None:
        triage = TriageResult("emergency_potential", "Pode ser uma emergencia", "Resumo")
        payload = self.engine.build(triage, "dor no peito")
        labels = [item["label"] for item in payload["actions"]]
        self.assertIn("Ligar 112", labels)

    def test_practical_medicine_shows_infarmed(self) -> None:
        triage = TriageResult("practical_health", "Opcoes disponiveis", "Resumo")
        payload = self.engine.build(triage, "preciso de um medicamento")
        titles = [item["title"] for item in payload["resources"]]
        self.assertEqual(titles[0], "Pesquisar medicamento")
        self.assertIn("Ver farmacias proximas", titles)

    def test_unvalidated_farmacias_note_is_exposed(self) -> None:
        triage = TriageResult("practical_health", "Opcoes disponiveis", "Resumo")
        payload = self.engine.build(triage, "farmacia aberta")
        self.assertTrue(any("indisponivel" in note.lower() for note in payload["notes"]))


if __name__ == "__main__":
    unittest.main()
