from __future__ import annotations

from core.providers.contracts import HealthStatus, Money, TextRequest, TextResult

ID = "local/fake"


class LocalFakeText:
    id = ID

    def estimate_cost(self, req: TextRequest) -> Money:
        return Money(usd=0.0)

    def health_check(self) -> HealthStatus:
        return HealthStatus(ok=True, detail="deterministic placeholder, no network")

    def generate(self, req: TextRequest) -> TextResult:
        text = f"[placeholder text for stage '{req.stage}']\n\n{req.prompt[:200]}"
        return TextResult(
            text=text,
            input_tokens=len(req.prompt.split()),
            output_tokens=len(text.split()),
            model=self.id,
        )


def get_adapter(model: str, options: dict) -> LocalFakeText:
    return LocalFakeText()
