from __future__ import annotations

from core.providers.contracts import HealthStatus, Money, ResearchQuery, ResearchResult

ID_PREFIX = "tavily"


class TavilyResearch:
    def __init__(self, model: str, options: dict):
        self.id = f"{ID_PREFIX}/{model}"
        self.model = model
        self.options = options

    def estimate_cost(self, req: ResearchQuery) -> Money:
        raise NotImplementedError("look up core/providers/pricing.yaml")

    def health_check(self) -> HealthStatus:
        return HealthStatus(ok=False, detail="Tavily adapter not implemented yet — see master plan §11 M1")

    def search(self, req: ResearchQuery) -> ResearchResult:
        raise NotImplementedError("call the Tavily search API here")


def get_adapter(model: str, options: dict) -> TavilyResearch:
    return TavilyResearch(model, options)
