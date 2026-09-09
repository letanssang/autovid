from __future__ import annotations

from core.providers.contracts import HealthStatus, PublishRequest, PublishResult

ID_PREFIX = "youtube"


class YouTubePublish:
    def __init__(self, model: str, options: dict):
        self.id = f"{ID_PREFIX}/{model}"
        self.model = model
        self.options = options

    def health_check(self) -> HealthStatus:
        return HealthStatus(ok=False, detail="YouTube adapter not implemented yet — see master plan §6 S7, §11 M4")

    def publish(self, req: PublishRequest) -> PublishResult:
        raise NotImplementedError("call the YouTube Data API v3 here — keep privacy='private', never auto-publish")


def get_adapter(model: str, options: dict) -> YouTubePublish:
    return YouTubePublish(model, options)
