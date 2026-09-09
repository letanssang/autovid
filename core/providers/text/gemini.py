from __future__ import annotations

from core.providers.contracts import HealthStatus, Money, TextRequest, TextResult

ID_PREFIX = "gemini"


class GeminiText:
    def __init__(self, model: str, options: dict):
        self.id = f"{ID_PREFIX}/{model}"
        self.model = model
        self.options = options

    def estimate_cost(self, req: TextRequest) -> Money:
        raise NotImplementedError("look up core/providers/pricing.yaml and estimate from prompt length")

    def health_check(self) -> HealthStatus:
        return HealthStatus(ok=False, detail="Gemini text adapter not implemented yet — see master plan §11 M1")

    def generate(self, req: TextRequest) -> TextResult:
        raise NotImplementedError("call the Gemini API here")


def get_adapter(model: str, options: dict) -> GeminiText:
    return GeminiText(model, options)
