from __future__ import annotations

from core.providers.contracts import HealthStatus, PublishRequest, PublishResult

ID = "local/only"


class LocalOnlyPublish:
    id = ID

    def health_check(self) -> HealthStatus:
        return HealthStatus(ok=True, detail="no upload — file stays local until you click Upload in the dashboard")

    def publish(self, req: PublishRequest) -> PublishResult:
        return PublishResult(url="", remote_id="")


def get_adapter(model: str, options: dict) -> LocalOnlyPublish:
    return LocalOnlyPublish()
