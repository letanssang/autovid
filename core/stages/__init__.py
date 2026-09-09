from __future__ import annotations

from core.stages import (
    s01_research,
    s02_outline,
    s03_script,
    s04_visual_plan,
    s05_assets,
    s06_render,
    s07_publish,
)

STAGE_RUNNERS = {
    "01_research": s01_research.run,
    "02_outline": s02_outline.run,
    "03_script": s03_script.run,
    "04_visual_plan": s04_visual_plan.run,
    "05_assets": s05_assets.run,
    "06_render": s06_render.run,
    "07_publish": s07_publish.run,
}
