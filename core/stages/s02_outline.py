from __future__ import annotations

import json
from pathlib import Path

from core.prompts import render_prompt
from core.providers.contracts import TextRequest
from core.providers.registry import Registry
from core.stages.s01_research import slug

STAGE = "02_outline"

WORDS_PER_MINUTE = 150  # matches the pacing assumption used across the pipeline
TARGET_SECTION_WORDS = 350  # ≈2.3 min/section — plan/phase-5-length-and-flow.md §5.1
TARGET_SECTION_SEC = TARGET_SECTION_WORDS / WORDS_PER_MINUTE * 60


def run(project_root: Path, config: dict) -> None:
    topic = config["topic"]
    locale = config.get("locales", ["en"])[0]
    fmt = config.get("format", "educational")
    target_minutes = config.get("video", {}).get("target_duration_minutes", [15, 25])
    revision_note = config.get("_revision_note", "")
    registry = Registry.from_project_yaml(project_root)
    text_provider = registry.resolve("text", stage=STAGE)

    research = json.loads((project_root / "01_research" / "research.json").read_text())
    angles = [a["angle"] for a in research["angles"]]
    research_by_angle = {a["angle"]: a["text"] for a in research["angles"]}

    # Size the outline to the target duration instead of a fixed 2 sections per
    # chapter (plan/phase-5-length-and-flow.md §5.1). Angles now come from
    # s01's dynamic proposal, so the chapter count itself already scales with
    # the target — this only decides how many sections fill each chapter.
    target_duration_sec = (sum(target_minutes) / 2) * 60
    target_section_count = max(1, round(target_duration_sec / TARGET_SECTION_SEC))
    sections_per_chapter = max(1, round(target_section_count / max(len(angles), 1)))

    chapters = []
    for angle in angles:
        chapter_title = angle.capitalize()
        sections = []
        for i in range(1, sections_per_chapter + 1):
            prompt = render_prompt(
                locale, fmt, "outline",
                chapter=chapter_title, section=f"Part {i}",
                research=research_by_angle.get(angle, ""),
                revision_note=revision_note,
            )
            result = text_provider.generate(TextRequest(prompt=prompt, stage=STAGE))
            sections.append({"id": f"{slug(angle)}-{i}", "title": result.text.strip()})
        chapters.append({"chapter_title": chapter_title, "sections": sections})

    total_sections = sum(len(ch["sections"]) for ch in chapters)
    section_duration_sec = target_duration_sec / max(total_sections, 1)

    out_dir = project_root / STAGE
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "outline.json").write_text(json.dumps({"topic": topic, "chapters": chapters}, indent=2))
    (out_dir / "outline.md").write_text(_render_markdown(topic, chapters, total_sections, section_duration_sec))


def _render_markdown(topic: str, chapters: list[dict], total_sections: int, section_duration_sec: float) -> str:
    lines = [
        f"# Outline: {topic}",
        "",
        (f"{total_sections} sections, ~{round(section_duration_sec)}s each "
         "(even split — real per-section timing lands in Phase 2 once TTS is real)."),
        "",
    ]
    for ch in chapters:
        lines.append(f"## {ch['chapter_title']}")
        lines.append("")
        for s in ch["sections"]:
            lines.append(f"- **{s['title']}** (`{s['id']}`, ~{round(section_duration_sec)}s)")
        lines.append("")
    return "\n".join(lines)
