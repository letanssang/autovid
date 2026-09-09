from __future__ import annotations

import json
from pathlib import Path

from core.prompts import render_prompt
from core.providers.contracts import TextRequest
from core.providers.registry import Registry
from core.stages.s01_research import slug

STAGE = "03_script"
WORDS_PER_MINUTE = 150  # matches the TTS fake stub's pacing assumption


def run(project_root: Path, config: dict) -> None:
    locale = config.get("locales", ["en"])[0]
    fmt = config.get("format", "educational")
    target_minutes = config.get("video", {}).get("target_duration_minutes", [15, 25])
    registry = Registry.from_project_yaml(project_root)
    text_provider = registry.resolve("text", stage=STAGE)

    outline = json.loads((project_root / "02_outline" / "outline.json").read_text())
    research = json.loads((project_root / "01_research" / "research.json").read_text())
    research_by_angle = {slug(a["angle"]): a["text"] for a in research["angles"]}

    all_sections = [s for ch in outline["chapters"] for s in ch["sections"]]
    target_duration_sec = (sum(target_minutes) / 2) * 60
    section_duration_sec = target_duration_sec / max(len(all_sections), 1)
    target_word_count = round(section_duration_sec / 60 * WORDS_PER_MINUTE)

    # Knowledge spine: prior section titles, fed back so later sections don't
    # redefine terms already introduced — see master plan §6 S3.
    spine_lines: list[str] = []
    sections_out = []
    for section in all_sections:
        angle = section["id"].rsplit("-", 1)[0]
        prompt = render_prompt(
            locale, fmt, "script",
            section_title=section["title"],
            target_duration_sec=round(section_duration_sec),
            research=research_by_angle.get(angle, ""),
            spine="\n".join(spine_lines) or "(none yet — this is the opening section)",
        )
        result = text_provider.generate(TextRequest(prompt=prompt, stage=STAGE))
        script_text = result.text.strip()
        sections_out.append({
            "id": section["id"],
            "title": section["title"],
            "script": script_text,
            "target_duration_sec": round(section_duration_sec),
            "target_word_count": target_word_count,
            "word_count": len(script_text.split()),
        })
        spine_lines.append(f"- {section['title']}")

    out_dir = project_root / STAGE
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "script.json").write_text(json.dumps({"sections": sections_out}, indent=2))
    (out_dir / "script.md").write_text(_render_markdown(sections_out))


def _render_markdown(sections: list[dict]) -> str:
    lines = ["# Script", ""]
    for s in sections:
        lines.append(f"## {s['title']} (`{s['id']}`)")
        lines.append("")
        lines.append(
            f"*{s['word_count']} words (target ~{s['target_word_count']}) — "
            f"target duration ~{s['target_duration_sec']}s*"
        )
        lines.append("")
        lines.append(s["script"])
        lines.append("")
    return "\n".join(lines)
