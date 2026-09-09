from __future__ import annotations

from core.providers.contracts import HealthStatus, Money, TTSRequest, TTSResult

ID_PREFIX = "elevenlabs"


class ElevenLabsTTS:
    def __init__(self, model: str, options: dict):
        self.id = f"{ID_PREFIX}/{model}"
        self.model = model
        self.options = options

    def estimate_cost(self, req: TTSRequest) -> Money:
        raise NotImplementedError("look up core/providers/pricing.yaml")

    def health_check(self) -> HealthStatus:
        return HealthStatus(ok=False, detail="ElevenLabs adapter not implemented yet — see master plan §11 M1")

    def synthesize(self, req: TTSRequest) -> TTSResult:
        raise NotImplementedError("call the ElevenLabs TTS API here")


def get_adapter(model: str, options: dict) -> ElevenLabsTTS:
    return ElevenLabsTTS(model, options)
