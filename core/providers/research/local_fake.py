from __future__ import annotations

from core.providers.contracts import (
    HealthStatus,
    Money,
    ResearchQuery,
    ResearchResult,
    ResearchSource,
)

ID = "local/fake"


class LocalFakeResearch:
    id = ID

    def estimate_cost(self, req: ResearchQuery) -> Money:
        return Money(usd=0.0)

    def health_check(self) -> HealthStatus:
        return HealthStatus(ok=True, detail="deterministic placeholder, no network")

    def search(self, req: ResearchQuery) -> ResearchResult:
        sources = [
            ResearchSource(
                url=f"https://example.com/placeholder-{i}",
                title=f"Placeholder source {i} for '{req.query}'",
                snippet="Wire up a real research provider (core/providers/research/) before trusting this.",
                confidence=0.0,
            )
            for i in range(1, min(req.max_results, 3) + 1)
        ]
        return ResearchResult(sources=sources)


def get_adapter(model: str, options: dict) -> LocalFakeResearch:
    return LocalFakeResearch()
