from __future__ import annotations

from pathlib import Path

import yaml

PRICING_PATH = Path(__file__).resolve().parent / "pricing.yaml"


def _load() -> dict:
    return yaml.safe_load(PRICING_PATH.read_text()) or {}


def text_cost_usd(provider_id: str, input_tokens: int, output_tokens: int) -> float | None:
    """Real cost for a text call from pricing.yaml, or None if the provider has no entry
    (e.g. an opaque self-hosted router) — caller should fall back to its own estimate."""
    rates = _load().get("text", {}).get(provider_id)
    if not rates:
        return None
    return (input_tokens / 1_000_000) * rates.get("input_per_1m", 0.0) + (
        output_tokens / 1_000_000
    ) * rates.get("output_per_1m", 0.0)


def tts_cost_usd(provider_id: str, char_count: int) -> float | None:
    """Real cost for a TTS call from pricing.yaml's per_1m_chars rate, or None if
    the provider has no entry — caller should fall back to its own estimate."""
    rates = _load().get("tts", {}).get(provider_id)
    if not rates:
        return None
    return (char_count / 1_000_000) * rates.get("per_1m_chars", 0.0)
