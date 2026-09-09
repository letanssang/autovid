from __future__ import annotations

import json
from pathlib import Path

STAGE = "04_visual_plan"

# Deterministic heuristic for now — see prompts/en/educational/visual.md for
# the LLM-based classifier this is meant to be replaced/augmented with later.
VISUAL_TYPES = ["title", "diagram", "code", "comparison", "ai_image", "b_roll"]


def run(project_root: Path, config: dict) -> None:
    max_ai_images = config.get("budget", {}).get("max_ai_images", 15)
    script = json.loads((project_root / "03_script" / "script.json").read_text())

    plan = []
    ai_image_count = 0
    downgraded = 0
    previous_type = None
    type_idx = 0

    for section in script["sections"]:
        beats = _split_beats(section["script"])
        for i, beat_text in enumerate(beats):
            visual_type = VISUAL_TYPES[type_idx % len(VISUAL_TYPES)]
            type_idx += 1
            if visual_type == previous_type:
                visual_type = VISUAL_TYPES[type_idx % len(VISUAL_TYPES)]
                type_idx += 1

            if visual_type == "ai_image":
                if ai_image_count >= max_ai_images:
                    visual_type = "b_roll"
                    downgraded += 1
                else:
                    ai_image_count += 1

            plan.append({
                "section_id": section["id"],
                "beat_index": i,
                "text": beat_text,
                "visual_type": visual_type,
            })
            previous_type = visual_type

    out_dir = project_root / STAGE
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "visual_plan.json").write_text(json.dumps({
        "beats": plan,
        "ai_image_count": ai_image_count,
        "ai_image_budget": max_ai_images,
        "downgraded_to_b_roll": downgraded,
    }, indent=2))
    (out_dir / "visual_plan.md").write_text(
        _render_markdown(plan, ai_image_count, max_ai_images, downgraded)
    )


def _split_beats(script_text: str) -> list[str]:
    sentences = [s.strip() for s in script_text.replace("\n", " ").split(". ") if s.strip()]
    return sentences or [script_text]


def _render_markdown(plan: list[dict], ai_image_count: int, max_ai_images: int, downgraded: int) -> str:
    lines = [
        "# Visual plan",
        "",
        f"{len(plan)} beats — {ai_image_count}/{max_ai_images} AI images used"
        + (f", {downgraded} downgraded to b_roll" if downgraded else "") + ".",
        "",
        "| Section | Beat | Visual type | Narration |",
        "| --- | --- | --- | --- |",
    ]
    for beat in plan:
        snippet = beat["text"][:60].replace("|", "\\|").replace("\n", " ")
        if len(beat["text"]) > 60:
            snippet += "…"
        lines.append(f"| {beat['section_id']} | {beat['beat_index']} | {beat['visual_type']} | {snippet} |")
    return "\n".join(lines)
