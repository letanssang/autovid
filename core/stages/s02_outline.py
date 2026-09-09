from __future__ import annotations

import json
from pathlib import Path

from core.prompts import render_prompt
from core.providers.contracts import TextRequest
from core.providers.registry import Registry
from core.stages.s01_research import RESEARCH_ANGLES, slug

STAGE = "02_outline"
SECTIONS_PER_CHAPTER = 2


def run(project_root: Path, config: dict) -> None:
    topic = config["topic"]
    locale = config.get("locales", ["en"])[0]
    fmt = config.get("format", "educational")
    target_minutes = config.get("video", {}).get("target_duration_minutes", [15, 25])
    registry = Registry.from_project_yaml(project_root)
    text_provider = registry.resolve("text", stage=STAGE)

    research = json.loads((project_root / "01_research" / "research.json").read_text())
    research_by_angle = {a["angle"]: a["text"] for a in research["angles"]}

    chapters = []
    for angle in RESEARCH_ANGLES:
        chapter_title = angle.capitalize()
        sections = []
        for i in range(1, SECTIONS_PER_CHAPTER + 1):
            prompt = render_prompt(
                locale, fmt, "outline",
                chapter=chapter_title, section=f"Part {i}",
                research=research_by_angle.get(angle, ""),
            )
            result = text_provider.generate(TextRequest(prompt=prompt, stage=STAGE))
            sections.append({"id": f"{slug(angle)}-{i}", "title": result.text.strip()})
        chapters.append({"chapter_title": chapter_title, "sections": sections})

    total_sections = sum(len(ch["sections"]) for ch in chapters)
    target_duration_sec = (sum(target_minutes) / 2) * 60
    section_duration_sec = target_duration_sec / max(total_sections, 1)

    out_dir = project_root / STAGE
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "outline.json").write_text(json.dumps({"topic": topic, "chapters": chapters}, indent=2))
    (out_dir / "outline.md").write_text(
        _render_markdown(topic, chapters, total_sections, section_duration_sec)
    )


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
