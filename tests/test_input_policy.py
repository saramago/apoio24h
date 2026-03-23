import unittest

from core.input_policy import (
    AMBIGUOUS_DEBOUNCE_MS,
    DEFAULT_DEBOUNCE_MS,
    VOICE_END_SILENCE_SECONDS,
    debounce_delay_ms,
    normalize_input_text,
    should_auto_submit_text,
    should_auto_submit_voice,
    should_submit_voice_after_silence,
)


class InputPolicyTests(unittest.TestCase):
    def test_normalize_input_text(self) -> None:
        self.assertEqual(normalize_input_text("  Dor   no peito!!! "), "dor no peito")
        self.assertEqual(normalize_input_text("Hospital, mais próximo?"), "hospital mais próximo")

    def test_text_auto_submit_useful_inputs(self) -> None:
        cases = [
            "preciso de medicamento",
            "farmacia aberta",
            "dor no peito",
            "stress",
            "não sei o que fazer",
            "hospital mais proximo",
            "sns 24",
        ]
        for case in cases:
            with self.subTest(case=case):
                self.assertTrue(should_auto_submit_text(case))

    def test_text_auto_submit_blocks_ambiguous_inputs(self) -> None:
        for case in ("falar", "ajuda", "dor", "ola"):
            with self.subTest(case=case):
                self.assertFalse(should_auto_submit_text(case))

    def test_debounce_is_longer_for_ambiguous_short_terms(self) -> None:
        self.assertEqual(debounce_delay_ms("hospital"), AMBIGUOUS_DEBOUNCE_MS)
        self.assertEqual(debounce_delay_ms("farmacia"), AMBIGUOUS_DEBOUNCE_MS)
        self.assertEqual(debounce_delay_ms("preciso de medicamento"), DEFAULT_DEBOUNCE_MS)

    def test_voice_submission_accepts_useful_transcripts(self) -> None:
        for case in ("dor no peito", "farmacia aberta", "stress", "não sei o que fazer"):
            with self.subTest(case=case):
                self.assertTrue(should_auto_submit_voice(case))

    def test_voice_submission_rejects_empty_or_too_ambiguous_transcripts(self) -> None:
        for case in ("", " ", "dor", "ajuda", "falar"):
            with self.subTest(case=case):
                self.assertFalse(should_auto_submit_voice(case))

    def test_voice_submission_waits_for_silence(self) -> None:
        self.assertFalse(should_submit_voice_after_silence("preciso de medicamento", VOICE_END_SILENCE_SECONDS - 0.1))
        self.assertTrue(should_submit_voice_after_silence("preciso de medicamento", VOICE_END_SILENCE_SECONDS))


if __name__ == "__main__":
    unittest.main()
