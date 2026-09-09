from __future__ import annotations

from core.providers.contracts import (
    HealthStatus,
    ImageCaps,
    ImageRequest,
    ImageResult,
    Money,
)

ID_PREFIX = "sdxl"


class SDXLLocalImage:
    def __init__(self, model: str, options: dict):
        self.id = f"{ID_PREFIX}/{model}"
        self.model = model
        self.options = options
        self.caps = ImageCaps(resolutions=["1024x1024"], batch=False, edit=False, text_in_image=False)

    def estimate_cost(self, req: ImageRequest) -> Money:
        return Money(usd=0.0)  # local inference — free

    def health_check(self) -> HealthStatus:
        return HealthStatus(ok=False, detail="SDXL local adapter not implemented yet — see master plan §9.2 (image.fallback)")

    def generate(self, req: ImageRequest) -> ImageResult:
        raise NotImplementedError("run local SDXL inference here")


def get_adapter(model: str, options: dict) -> SDXLLocalImage:
    return SDXLLocalImage(model, options)
