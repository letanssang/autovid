from __future__ import annotations

from core.providers.contracts import (
    HealthStatus,
    Money,
    VideoClipRequest,
    VideoClipResult,
)

ID_PREFIX = "veo"


class VeoVideoClip:
    def __init__(self, model: str, options: dict):
        self.id = f"{ID_PREFIX}/{model}"
        self.model = model
        self.options = options

    def estimate_cost(self, req: VideoClipRequest) -> Money:
        raise NotImplementedError("look up core/providers/pricing.yaml")

    def health_check(self) -> HealthStatus:
        return HealthStatus(ok=False, detail="Veo adapter not implemented yet — off by default, see master plan §9.2")

    def generate(self, req: VideoClipRequest) -> VideoClipResult:
        raise NotImplementedError("call the Veo API here")


def get_adapter(model: str, options: dict) -> VeoVideoClip:
    return VeoVideoClip(model, options)
