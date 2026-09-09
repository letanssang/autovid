from __future__ import annotations

from core.providers.contracts import HealthStatus, Money, TextRequest, TextResult

ID_PREFIX = "ollama"


class OllamaText:
    def __init__(self, model: str, options: dict):
        self.id = f"{ID_PREFIX}/{model}"
        self.model = model
        self.options = options

    def estimate_cost(self, req: TextRequest) -> Money:
        return Money(usd=0.0)  # local inference — free

    def health_check(self) -> HealthStatus:
        return HealthStatus(ok=False, detail="Ollama text adapter not implemented yet — see master plan §11 M1")

    def generate(self, req: TextRequest) -> TextResult:
        raise NotImplementedError("call the local Ollama HTTP API here")


def get_adapter(model: str, options: dict) -> OllamaText:
    return OllamaText(model, options)
