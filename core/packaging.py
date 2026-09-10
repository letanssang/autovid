from __future__ import annotations

import json
import shutil
from pathlib import Path

REQUIRED_SOURCES = {
    "video": ("06_render", "output.mp4"),
    "subtitles": ("06_render", "subtitles.srt"),
    "thumbnail": ("07_publish", "thumbnail.png"),
    "metadata": ("07_publish", "metadata.json"),
}


def package(project_root: Path) -> Path:
    """Assembles everything needed for a manual YouTube upload into
    07_publish/upload/ (plan/phase-6-publish-package.md §6.4). Raises
    FileNotFoundError naming the first missing/empty prerequisite rather than
    silently producing a partial folder — a human is about to trust this
    folder for a real upload."""
    paths = {}
    for key, (stage_dir, filename) in REQUIRED_SOURCES.items():
        path = project_root / stage_dir / filename
        if not path.exists() or path.stat().st_size == 0:
            raise FileNotFoundError(
                f"missing or empty {stage_dir}/{filename} — run the pipeline through {stage_dir} first"
            )
        paths[key] = path

    metadata = json.loads(paths["metadata"].read_text())

    upload_dir = project_root / "07_publish" / "upload"
    upload_dir.mkdir(parents=True, exist_ok=True)

    shutil.copy(paths["video"], upload_dir / "video.mp4")
    shutil.copy(paths["thumbnail"], upload_dir / "thumbnail.png")
    shutil.copy(paths["subtitles"], upload_dir / "subtitles.srt")
    # title.txt isn't in the plan's literal file list, but a human doing a
    # manual upload needs the title text somewhere to copy — leaving it out
    # would contradict the stage's own goal ("everything needed").
    (upload_dir / "title.txt").write_text(metadata.get("title", ""))
    (upload_dir / "description.txt").write_text(metadata.get("description", ""))
    # Comma-separated on one line — pastes directly into YouTube Studio's tag field.
    (upload_dir / "tags.txt").write_text(", ".join(metadata.get("tags", [])))

    return upload_dir
