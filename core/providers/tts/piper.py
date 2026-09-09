from __future__ import annotations

from core.providers.contracts import HealthStatus, Money, TTSRequest, TTSResult

ID_PREFIX = "piper"


class PiperTTS:
    def __init__(self, model: str, options: dict):
        self.id = f"{ID_PREFIX}/{model}"
        self.model = model
        self.options = options

    def estimate_cost(self, req: TTSRequest) -> Money:
        return Money(usd=0.0)  # local inference — free, this is the offline fallback

    def health_check(self) -> HealthStatus:
        return HealthStatus(ok=False, detail="Piper adapter not implemented yet — see master plan §9.2 (tts.fallback)")

    def synthesize(self, req: TTSRequest) -> TTSResult:
        raise NotImplementedError("call local Piper TTS binary here")


def get_adapter(model: str, options: dict) -> PiperTTS:
    return PiperTTS(model, options)
