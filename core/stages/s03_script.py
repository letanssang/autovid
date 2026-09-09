from __future__ import annotations

import json
from pathlib import Path

from core.prompts import render_prompt
from core.providers.contracts import TextRequest
from core.providers.registry import Registry
from core.stages.s01_research import slug

STAGE = "03_script"
WORDS_PER_MINUTE = 150  # matches the TTS fake stub's pacing assumption

MAX_RETRIES = 2  # plan/phase-5-length-and-flow.md §5.2 cost guardrail: 1 + 2 retries/section
WORD_COUNT_TOLERANCE = 0.25

HOOK_TARGET_SEC = 30
OUTRO_TARGET_SEC = 25


def run(project_root: Path, config: dict) -> None:
    locale = config.get("locales", ["en"])[0]
    fmt = config.get("format", "educational")
    target_minutes = config.get("video", {}).get("target_duration_minutes", [15, 25])
    registry = Registry.from_project_yaml(project_root)
    text_provider = registry.resolve("text", stage=STAGE)

    outline = json.loads((project_root / "02_outline" / "outline.json").read_text())
    research = json.loads((project_root / "01_research" / "research.json").read_text())
    research_by_angle = {slug(a["angle"]): a["text"] for a in research["angles"]}

    topic = outline["topic"]
    all_sections = [s for ch in outline["chapters"] for s in ch["sections"]]
    target_duration_sec = (sum(target_minutes) / 2) * 60
    main_duration_sec = max(target_duration_sec - HOOK_TARGET_SEC - OUTRO_TARGET_SEC, 0)
    section_duration_sec = main_duration_sec / max(len(all_sections), 1)
    target_word_count = round(section_duration_sec / 60 * WORDS_PER_MINUTE)

    # Knowledge spine: prior section titles plus the key terms each one
    # introduced, fed back so later sections don't redefine the same term or
    # fact (plan/phase-5-length-and-flow.md §5.4 — titles alone catch topic
    # repeats but not fact/definition repeats across different sections).
    spine_lines: list[str] = []
    sections_out = []
    warnings: list[str] = []
    for section in all_sections:
        angle = section["id"].rsplit("-", 1)[0]
        script_text, key_terms, retries = _generate_section_script(
            text_provider, locale, fmt,
            section_title=section["title"],
            target_duration_sec=round(section_duration_sec),
            target_word_count=target_word_count,
            research=research_by_angle.get(angle, ""),
            spine="\n".join(spine_lines) or "(none yet — this is the opening section)",
        )
        word_count = len(script_text.split())
        deviation = abs(word_count - target_word_count) / max(target_word_count, 1)
        if retries >= MAX_RETRIES and deviation > WORD_COUNT_TOLERANCE:
            warnings.append(
                f"{section['id']}: {word_count} words vs target {target_word_count} "
                f"(still off by {deviation:.0%} after {retries} retries)"
            )
        sections_out.append({
            "id": section["id"],
            "title": section["title"],
            "script": script_text,
            "target_duration_sec": round(section_duration_sec),
            "target_word_count": target_word_count,
            "word_count": word_count,
            "retries": retries,
        })
        spine_entry = f"- {section['title']}"
        if key_terms:
            spine_entry += f" (introduces: {', '.join(key_terms)})"
        spine_lines.append(spine_entry)

    # Hook and outro are generated last, outside the per-chapter loop, then
    # placed first/last in the section list (plan/phase-5-length-and-flow.md
    # §5.3). The hook needs the full outline to promise what the video
    # actually answers, so it's written after everything else even though it
    # plays first.
    outline_summary = "\n".join(f"- {s['title']}" for s in all_sections)
    full_spine = "\n".join(spine_lines)
    outro_entry = _generate_special_section(
        text_provider, locale, fmt, "outro",
        topic=topic, outline_summary=outline_summary, spine=full_spine, target_sec=OUTRO_TARGET_SEC,
    )
    hook_entry = _generate_special_section(
        text_provider, locale, fmt, "hook",
        topic=topic, outline_summary=outline_summary, spine=full_spine, target_sec=HOOK_TARGET_SEC,
    )
    sections_out.append(outro_entry)
    sections_out.insert(0, hook_entry)

    out_dir = project_root / STAGE
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "script.json").write_text(json.dumps({"sections": sections_out}, indent=2))
    (out_dir / "script.md").write_text(_render_markdown(sections_out, warnings))


def _generate_section_script(
    text_provider, locale: str, fmt: str, *,
    section_title: str, target_duration_sec: int, target_word_count: int, research: str, spine: str,
) -> tuple[str, list[str], int]:
    """Generates narration for one section, retrying up to MAX_RETRIES times
    when the word count deviates from target by more than WORD_COUNT_TOLERANCE
    (plan/phase-5-length-and-flow.md §5.2). Each retry feeds the model its own
    previous draft plus a concrete instruction (add an example, a stat from
    research, go deeper on a point — or tighten wording) rather than a vague
    "write longer/shorter", which just produces filler or lost content.

    generate() is called unwrapped on every attempt so BudgetExceeded still
    propagates and stops the pipeline — only response parsing has a fallback.
    """
    previous_draft = ""
    previous_word_count = 0
    length_instruction = ""
    for attempt in range(MAX_RETRIES + 1):
        prompt = render_prompt(
            locale, fmt, "script",
            section_title=section_title,
            target_duration_sec=target_duration_sec,
            target_word_count=target_word_count,
            research=research,
            spine=spine,
            length_instruction=length_instruction,
            previous_draft=previous_draft,
            previous_word_count=previous_word_count,
        )
        result = text_provider.generate(TextRequest(prompt=prompt, stage=STAGE))
        script_text, key_terms = _split_script_and_terms(result.text.strip())
        word_count = len(script_text.split())
        deviation = abs(word_count - target_word_count) / max(target_word_count, 1)

        if deviation <= WORD_COUNT_TOLERANCE or attempt == MAX_RETRIES:
            return script_text, key_terms, attempt

        previous_draft = script_text
        previous_word_count = word_count
        if word_count < target_word_count:
            length_instruction = (
                "That draft was too short. Expand it: add a concrete example, a "
                "number or fact from the research notes, or go one level deeper on "
                "a point already made. Do not just add filler words."
            )
        else:
            length_instruction = (
                "That draft was too long. Tighten the wording and cut redundant "
                "phrasing, but keep every idea — don't drop content wholesale."
            )
    raise AssertionError("unreachable")  # loop always returns on attempt == MAX_RETRIES


def _generate_special_section(
    text_provider, locale: str, fmt: str, kind: str, *,
    topic: str, outline_summary: str, spine: str, target_sec: int,
) -> dict:
    """Single-shot generation for the hook/outro — no word-count retry loop,
    per plan/phase-5-length-and-flow.md §5.3 (only §5.2's main sections get
    the retry treatment)."""
    target_word_count = round(target_sec / 60 * WORDS_PER_MINUTE)
    prompt = render_prompt(
        locale, fmt, kind,
        topic=topic, outline_summary=outline_summary, spine=spine, target_word_count=target_word_count,
    )
    result = text_provider.generate(TextRequest(prompt=prompt, stage=STAGE))
    script_text, _key_terms = _split_script_and_terms(result.text.strip())
    return {
        "id": kind,
        "title": kind.capitalize(),
        "script": script_text,
        "target_duration_sec": target_sec,
        "target_word_count": target_word_count,
        "word_count": len(script_text.split()),
        "retries": 0,
    }


def _split_script_and_terms(text: str) -> tuple[str, list[str]]:
    """Strips a trailing 'KEY_TERMS: a, b, c' line the script prompt asks for
    (plan/phase-5-length-and-flow.md §5.4) — it feeds the knowledge spine, not
    the narration, so it must never reach word_count or the TTS input."""
    lines = text.splitlines()
    while lines and not lines[-1].strip():
        lines.pop()
    key_terms: list[str] = []
    if lines and lines[-1].strip().upper().startswith("KEY_TERMS:"):
        terms_line = lines.pop().split(":", 1)[1]
        key_terms = [t.strip() for t in terms_line.split(",") if t.strip()]
    return "\n".join(lines).strip(), key_terms


def _render_markdown(sections: list[dict], warnings: list[str]) -> str:
    lines = ["# Script", ""]
    if warnings:
        lines.append("**Warnings (word count still off target after max retries):**")
        lines += [f"- {w}" for w in warnings]
        lines.append("")
    for s in sections:
        retry_note = f" — retried {s['retries']}x" if s.get("retries") else ""
        lines.append(f"## {s['title']} (`{s['id']}`){retry_note}")
        lines.append("")
        lines.append(
            f"*{s['word_count']} words (target ~{s['target_word_count']}) — "
            f"target duration ~{s['target_duration_sec']}s*"
        )
        lines.append("")
        lines.append(s["script"])
        lines.append("")
    return "\n".join(lines)
