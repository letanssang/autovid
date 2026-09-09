from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

STAGES = [
    "01_research",
    "02_outline",
    "03_script",
    "04_visual_plan",
    "05_assets",
    "06_render",
    "07_publish",
]

# Stages with a human approval gate (a `.approved` file). 05/06/07 run
# automatically once 04_visual_plan is approved — the only remaining human
# checkpoint is the manual Upload click in 07_publish, which isn't a
# filesystem gate.
GATED_STAGES = {"01_research", "02_outline", "03_script", "04_visual_plan"}


@dataclass
class ProjectState:
    root: Path

    @property
    def config_path(self) -> Path:
        return self.root / "project.yaml"

    def load_config(self) -> dict:
        return yaml.safe_load(self.config_path.read_text())

    def stage_dir(self, stage: str) -> Path:
        d = self.root / stage
        d.mkdir(parents=True, exist_ok=True)
        return d

    def is_approved(self, stage: str) -> bool:
        return (self.stage_dir(stage) / ".approved").exists()

    def approve(self, stage: str) -> None:
        (self.stage_dir(stage) / ".approved").touch()

    def has_run(self, stage: str) -> bool:
        artifacts = [p for p in self.stage_dir(stage).iterdir() if p.name != ".approved"]
        return len(artifacts) > 0
