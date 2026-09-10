from __future__ import annotations

import json
from pathlib import Path

from core.prompts import parse_json_response, render_prompt
from core.providers.contracts import TextRequest
from core.providers.registry import Registry

STAGE = "04_visual_plan"

VISUAL_TYPES = ["title", "code", "diagram", "comparison", "ai_image", "b_roll"]
LLM_CONTENT_TYPES = {"code", "diagram", "comparison"}
BATCH_SIZE = 20  # beats per classification request — see plan/phase-4-right-visuals.md §4.1


def run(project_root: Path, config: dict) -> None:
    locale = config.get("locales", ["en"])[0]
    fmt = config.get("format", "educational")
    max_ai_images = config.get("budget", {}).get("max_ai_images", 15)
    revision_note = config.get("_revision_note", "")
    registry = Registry.from_project_yaml(project_root)
    text_provider = registry.resolve("text", stage=STAGE)

    script = json.loads((project_root / "03_script" / "script.json").read_text())

    all_beats = []
    for section in script["sections"]:
        for i, beat_text in enumerate(_split_beats(section["script"])):
            all_beats.append({"section_id": section["id"], "beat_index": i, "text": beat_text})

    classifications, notes = _classify_beats(text_provider, locale, fmt, all_beats, max_ai_images, revision_note)

    plan = []
    ai_image_count = 0
    downgraded = 0
    previous_type = None

    for beat, classification in zip(all_beats, classifications):
        visual_type = classification["visual_type"]
        reason = classification["reason"]

        # Validate output: never trust the model's type as one of the 6 real
        # ones — fall back to title and log it (plan/phase-4-right-visuals.md §4.1).
        if visual_type not in VISUAL_TYPES:
            notes.append(
                f"{beat['section_id']}-{beat['beat_index']}: model returned invalid type "
                f"'{visual_type}', fell back to title"
            )
            visual_type = "title"
            reason = "fallback: model returned an invalid visual type"

        visual_type, reason = _avoid_repeat(visual_type, previous_type, reason)

        if visual_type == "ai_image":
            if ai_image_count >= max_ai_images:
                visual_type = "b_roll"
                downgraded += 1
                reason += " (downgraded: AI-image budget exhausted)"
            else:
                ai_image_count += 1

        visual_type, slide_content = _build_slide_content(
            text_provider, locale, fmt, visual_type, beat, notes, revision_note
        )
        # Content generation can itself downgrade the type (e.g. unparseable
        # code/diagram/comparison JSON falls back to a title slide) — re-check
        # the no-repeat constraint against that final type.
        visual_type, reason = _avoid_repeat(visual_type, previous_type, reason)
        if visual_type == "b_roll" and "quote" not in slide_content:
            slide_content = {"quote": beat["text"]}
        elif visual_type == "title" and "title" not in slide_content:
            slide_content = {"title": beat["text"]}

        plan.append({
            "section_id": beat["section_id"],
            "beat_index": beat["beat_index"],
            "text": beat["text"],
            "visual_type": visual_type,
            "reason": reason,
            "slide_content": slide_content,
        })
        previous_type = visual_type

    out_dir = project_root / STAGE
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "visual_plan.json").write_text(json.dumps({
        "beats": plan,
        "ai_image_count": ai_image_count,
        "ai_image_budget": max_ai_images,
        "downgraded_to_b_roll": downgraded,
        "notes": notes,
    }, indent=2))
    (out_dir / "visual_plan.md").write_text(
        _render_markdown(plan, ai_image_count, max_ai_images, downgraded, notes)
    )


def _avoid_repeat(visual_type: str, previous_type: str | None, reason: str) -> tuple[str, str]:
    """Enforce: no two consecutive beats share a visual type (kept from the
    original heuristic — it's correct, don't drop it, per plan/phase-4 §4.1)."""
    if visual_type != previous_type:
        return visual_type, reason
    fallback = "b_roll" if visual_type != "b_roll" else "title"
    return fallback, reason + " (adjusted: avoided repeating the previous beat's type)"


def _classify_beats(
    text_provider, locale: str, fmt: str, all_beats: list[dict], max_ai_images: int, revision_note: str = ""
) -> tuple[list[dict], list[str]]:
    """Classifies all beats in batches of BATCH_SIZE (one LLM call per batch,
    not per beat — see plan/phase-4-right-visuals.md §4.1 on cost). Falls back
    to `title` for any batch whose response doesn't parse into a same-length
    JSON array, logging the failure rather than crashing the stage."""
    notes: list[str] = []
    classifications: list[dict] = []
    previous_type_hint: str | None = None
    remaining_budget_hint = max_ai_images

    for batch_start in range(0, len(all_beats), BATCH_SIZE):
        batch = all_beats[batch_start : batch_start + BATCH_SIZE]
        prompt = render_prompt(
            locale, fmt, "visual",
            beats=batch,
            previous_visual_type=previous_type_hint,
            remaining_ai_images=remaining_budget_hint,
            revision_note=revision_note,
        )
        result = text_provider.generate(TextRequest(prompt=prompt, stage=STAGE))
        try:
            parsed = parse_json_response(result.text)
            if not isinstance(parsed, list) or len(parsed) != len(batch):
                raise ValueError(f"expected a {len(batch)}-item JSON array")
            batch_classifications = [
                {
                    "visual_type": str(item.get("visual_type", "")).strip(),
                    "reason": str(item.get("reason", "")).strip() or "(no reason given)",
                }
                for item in parsed
            ]
        except (ValueError, AttributeError, TypeError, KeyError) as e:
            notes.append(
                f"beats {batch_start}-{batch_start + len(batch) - 1}: could not parse batch "
                f"classification response ({e}) — all fell back to title"
            )
            batch_classifications = [
                {"visual_type": "title", "reason": "fallback: batch classification failed"} for _ in batch
            ]

        classifications.extend(batch_classifications)
        previous_type_hint = batch_classifications[-1]["visual_type"]
        remaining_budget_hint = max(
            remaining_budget_hint - sum(1 for c in batch_classifications if c["visual_type"] == "ai_image"), 0
        )

    return classifications, notes


def _build_slide_content(
    text_provider, locale: str, fmt: str, visual_type: str, beat: dict, notes: list[str], revision_note: str = ""
) -> tuple[str, dict]:
    """Generates the schema-correct slide content for this beat's visual type
    — the gated stage must produce reviewable content, not just a type label,
    since s05_assets.py only renders (plan/phase-4-right-visuals.md §4.2).
    `title` and `b_roll` need no LLM call: both are built deterministically
    from the beat's own narration."""
    if visual_type == "title":
        return visual_type, {"title": beat["text"]}
    if visual_type == "b_roll":
        return visual_type, {"quote": beat["text"]}
    if visual_type == "ai_image" or visual_type not in LLM_CONTENT_TYPES:
        return visual_type, {}

    prompt = render_prompt(
        locale, fmt, "slide_content", visual_type=visual_type, beat_text=beat["text"], revision_note=revision_note
    )
    result = text_provider.generate(TextRequest(prompt=prompt, stage=STAGE))
    try:
        content = parse_json_response(result.text)
        if not isinstance(content, dict) or not content:
            raise ValueError("expected a non-empty JSON object")
        return visual_type, content
    except (ValueError, AttributeError, TypeError) as e:
        beat_id = f"{beat['section_id']}-{beat['beat_index']}"
        notes.append(f"{beat_id}: could not parse {visual_type} slide content ({e}) — downgraded to title")
        return "title", {"title": beat["text"]}


MIN_BEAT_WORDS = 30
TARGET_BEAT_WORDS = 40
MAX_BEAT_WORDS = 50


def _split_beats(script_text: str) -> list[str]:
    """Groups sentences into beats aiming for TARGET_BEAT_WORDS (~12-20s at
    150 wpm) instead of one beat per sentence — a beat every ~7s (the old
    per-sentence split) changes the visual too fast to watch comfortably on a
    15-40 min video (plan/phase-5-length-and-flow.md §5.5)."""
    sentences = [s.strip() for s in script_text.replace("\n", " ").split(". ") if s.strip()]
    if not sentences:
        return [script_text]

    beats: list[list[str]] = []
    current: list[str] = []
    current_words = 0
    for sentence in sentences:
        words = len(sentence.split())
        if current and current_words + words > MAX_BEAT_WORDS and current_words >= MIN_BEAT_WORDS:
            beats.append(current)
            current, current_words = [], 0
        current.append(sentence)
        current_words += words
        if current_words >= TARGET_BEAT_WORDS:
            beats.append(current)
            current, current_words = [], 0

    if current:
        if beats and current_words < MIN_BEAT_WORDS:
            beats[-1].extend(current)
        else:
            beats.append(current)

    return [". ".join(b) for b in beats]


def _render_markdown(
    plan: list[dict], ai_image_count: int, max_ai_images: int, downgraded: int, notes: list[str]
) -> str:
    lines = [
        "# Visual plan", "",
        f"{len(plan)} beats — {ai_image_count}/{max_ai_images} AI images used"
        + (f", {downgraded} downgraded to b_roll" if downgraded else "") + ".",
        "",
    ]
    if notes:
        lines.append("**Notes (fallbacks triggered during generation):**")
        lines += [f"- {n}" for n in notes]
        lines.append("")
    lines += [
        "| Section | Beat | Visual type | Reason | Narration | Content preview |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for beat in plan:
        snippet = beat["text"][:60].replace("|", "\\|").replace("\n", " ")
        if len(beat["text"]) > 60:
            snippet += "…"
        content_preview = json.dumps(beat["slide_content"])[:80].replace("|", "\\|")
        reason = beat["reason"].replace("|", "\\|")
        lines.append(
            f"| {beat['section_id']} | {beat['beat_index']} | {beat['visual_type']} | "
            f"{reason} | {snippet} | {content_preview} |"
        )
    return "\n".join(lines)
