from __future__ import annotations

import json
from pathlib import Path

from core.providers.contracts import PublishRequest
from core.providers.registry import Registry

STAGE = "07_publish"


def run(project_root: Path, config: dict) -> None:
    topic = config.get("topic", "")
    registry = Registry.from_project_yaml(project_root)
    publish_provider = registry.resolve("publish", stage=STAGE)

    video_path = project_root / "06_render" / "output.mp4"
    publish_options = (config.get("providers", {}).get("publish", {}) or {}).get("options", {}) or {}

    metadata = {
        "title": topic,
        "description": f"An educational video about {topic}.\n\nGenerated with AutoVid.",
        "tags": [t.strip() for t in topic.split() if t.strip()][:15],
        "privacy": publish_options.get("privacy", "private"),
    }

    out_dir = project_root / STAGE
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

    thumbnail_path = out_dir / "thumbnail.png"
    if not thumbnail_path.exists():
        thumbnail_path.write_bytes(b"")  # replace with a real thumbnail — see core/providers/image/

    if publish_provider is None:
        return

    # local/only (default) is a no-op: the actual upload is a manual dashboard
    # click, never automatic — see AutoVid master plan §6 S7.
    publish_provider.publish(PublishRequest(
        video_path=str(video_path),
        title=metadata["title"],
        description=metadata["description"],
        tags=metadata["tags"],
        thumbnail_path=str(thumbnail_path),
        privacy=metadata["privacy"],
    ))
