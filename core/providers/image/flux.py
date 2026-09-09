from __future__ import annotations

from core.providers.contracts import (
    HealthStatus,
    ImageCaps,
    ImageRequest,
    ImageResult,
    Money,
)

ID_PREFIX = "flux"


class FluxImage:
    def __init__(self, model: str, options: dict):
        self.id = f"{ID_PREFIX}/{model}"
        self.model = model
        self.options = options
        self.caps = ImageCaps(resolutions=["1920x1080"], batch=False, edit=False, text_in_image=False)

    def estimate_cost(self, req: ImageRequest) -> Money:
        raise NotImplementedError("look up core/providers/pricing.yaml")

    def health_check(self) -> HealthStatus:
        return HealthStatus(ok=False, detail="Flux adapter not implemented yet — see master plan §11 M3")

    def generate(self, req: ImageRequest) -> ImageResult:
        raise NotImplementedError("call the Flux (Black Forest Labs) API here")


def get_adapter(model: str, options: dict) -> FluxImage:
    return FluxImage(model, options)
