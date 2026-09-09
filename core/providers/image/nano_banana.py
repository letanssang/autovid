from __future__ import annotations

from core.providers.contracts import (
    HealthStatus,
    ImageCaps,
    ImageRequest,
    ImageResult,
    Money,
)

ID_PREFIX = "gemini"


class NanoBananaImage:
    def __init__(self, model: str, options: dict):
        self.id = f"{ID_PREFIX}/{model}"
        self.model = model
        self.options = options
        self.caps = ImageCaps(resolutions=["1920x1080"], batch=True, edit=True, text_in_image=False)

    def estimate_cost(self, req: ImageRequest) -> Money:
        batch = self.options.get("batch", True)
        return Money(usd=0.0168 if batch else 0.0336)  # see core/providers/pricing.yaml

    def health_check(self) -> HealthStatus:
        return HealthStatus(ok=False, detail="Nano Banana adapter not implemented yet — see master plan §11 M3")

    def generate(self, req: ImageRequest) -> ImageResult:
        raise NotImplementedError("call the Nano Banana (Gemini image) Batch API here")


def get_adapter(model: str, options: dict) -> NanoBananaImage:
    return NanoBananaImage(model, options)
