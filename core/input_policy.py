from __future__ import annotations

import re


DEFAULT_DEBOUNCE_MS = 900
AMBIGUOUS_DEBOUNCE_MS = 1200
MIN_SUBMIT_LENGTH = 4
VOICE_END_SILENCE_SECONDS = 1.5
BLOCKED_AMBIGUOUS_TERMS = {"dor", "ajuda", "ola", "falar"}
SLOW_AMBIGUOUS_TERMS = {"hospital", "farmacia"}


def normalize_input_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[.,!?;:()\[\]{}\"'`´]+", " ", (value or "").lower()).strip())


def debounce_delay_ms(value: str) -> int:
    normalized = normalize_input_text(value)
    if normalized in SLOW_AMBIGUOUS_TERMS:
        return AMBIGUOUS_DEBOUNCE_MS
    return DEFAULT_DEBOUNCE_MS


def should_auto_submit_text(value: str) -> bool:
    normalized = normalize_input_text(value)
    if not normalized or len(normalized) < MIN_SUBMIT_LENGTH:
        return False
    if normalized in BLOCKED_AMBIGUOUS_TERMS:
        return False
    return True


def should_auto_submit_voice(value: str) -> bool:
    normalized = normalize_input_text(value)
    if not normalized:
        return False
    return should_auto_submit_text(normalized)


def should_submit_voice_after_silence(value: str, silence_seconds: float) -> bool:
    if silence_seconds < VOICE_END_SILENCE_SECONDS:
        return False
    return should_auto_submit_voice(value)
