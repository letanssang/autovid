from __future__ import annotations

from core.providers.contracts import HealthStatus, Money, ResearchQuery, ResearchResult

ID_PREFIX = "gemini"


class GeminiGroundingResearch:
    def __init__(self, model: str, options: dict):
        self.id = f"{ID_PREFIX}/{model}"
        self.model = model
        self.options = options

    def estimate_cost(self, req: ResearchQuery) -> Money:
        return Money(usd=0.0)  # free up to 5k queries/month — see pricing.yaml

    def health_check(self) -> HealthStatus:
        return HealthStatus(ok=False, detail="Gemini grounding adapter not implemented yet — see master plan §11 M1")

    def search(self, req: ResearchQuery) -> ResearchResult:
        raise NotImplementedError("call Gemini with Google Search grounding here")


def get_adapter(model: str, options: dict) -> GeminiGroundingResearch:
    return GeminiGroundingResearch(model, options)
