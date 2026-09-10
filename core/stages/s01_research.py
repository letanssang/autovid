from __future__ import annotations

import json
import re
from pathlib import Path

from core.prompts import parse_json_response, render_prompt
from core.providers.contracts import ResearchQuery, TextRequest
from core.providers.registry import Registry

STAGE = "01_research"

# Safety net for _propose_angles: used when the model's dynamic angle
# proposal fails to parse or returns too few usable angles — see
# plan/phase-5-length-and-flow.md §5.1 ("giữ 5 angle hiện tại làm fallback").
FALLBACK_ANGLES = [
    "overview",
    "how it works",
    "why it matters",
    "common misconceptions",
    "practical examples",
]

MIN_ANGLES = 3
MAX_ANGLES = 8


def slug(text: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return result or "section"


def run(project_root: Path, config: dict) -> None:
    topic = config["topic"]
    locale = config.get("locales", ["en"])[0]
    fmt = config.get("format", "educational")
    target_minutes = config.get("video", {}).get("target_duration_minutes", [15, 25])
    revision_note = config.get("_revision_note", "")
    registry = Registry.from_project_yaml(project_root)

    research_chain = _research_chain(registry)
    text_provider = registry.resolve("text", stage=STAGE)

    angle_names = _propose_angles(text_provider, locale, fmt, topic, target_minutes, revision_note)

    angles = []
    for angle in angle_names:
        sources, provider_used = _search_with_fallback(research_chain, ResearchQuery(query=f"{topic} {angle}"))
        prompt = render_prompt(locale, fmt, "research", topic=topic, angle=angle, revision_note=revision_note)
        text_result = text_provider.generate(TextRequest(prompt=prompt, stage=STAGE))
        angles.append({
            "angle": angle,
            "text": text_result.text,
            "research_provider": provider_used,
            "sources": [
                {"url": s.url, "title": s.title, "snippet": s.snippet, "confidence": s.confidence}
                for s in sources
            ],
        })

    out_dir = project_root / STAGE
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "research.json").write_text(json.dumps({"topic": topic, "angles": angles}, indent=2))
    (out_dir / "research.md").write_text(_render_markdown(topic, angles))


def _propose_angles(
    text_provider, locale: str, fmt: str, topic: str, target_minutes: list[int], revision_note: str = ""
) -> list[str]:
    """Sizes the angle list to the target video length instead of a fixed 5
    (plan/phase-5-length-and-flow.md §5.1) — a longer video needs more distinct
    angles, not a longer treatment of the same ones. The generate() call is
    left unwrapped so BudgetExceeded still propagates and stops the pipeline;
    only the response-parsing step falls back to FALLBACK_ANGLES."""
    avg_minutes = round(sum(target_minutes) / 2)
    prompt = render_prompt(locale, fmt, "angles", topic=topic, target_minutes=avg_minutes, revision_note=revision_note)
    result = text_provider.generate(TextRequest(prompt=prompt, stage=STAGE))

    try:
        parsed = parse_json_response(result.text)
        angle_names = [str(a).strip() for a in parsed if str(a).strip()]
    except (ValueError, AttributeError, TypeError):
        return list(FALLBACK_ANGLES)

    seen: set[str] = set()
    deduped = []
    for a in angle_names:
        key = a.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(a)

    if len(deduped) < MIN_ANGLES:
        return list(FALLBACK_ANGLES)
    return deduped[:MAX_ANGLES]


def _research_chain(registry: Registry) -> list:
    """Primary research provider plus its configured fallback chain (project.yaml
    providers.research.fallback), each resolved and cost-metered like the primary."""
    primary = registry.resolve("research", stage=STAGE)
    fallbacks = [registry.resolve_provider("research", pid) for pid in registry.fallback_chain("research")]
    return [p for p in [primary, *fallbacks] if p is not None]


def _search_with_fallback(chain: list, query: ResearchQuery) -> tuple[list, str]:
    """Try each provider in the chain in order; return the first one that
    succeeds, tagged with its id so research.md shows what actually served it."""
    if not chain:
        raise ValueError("No research provider configured — see project.yaml providers.research")
    last_error: Exception | None = None
    for provider in chain:
        try:
            return provider.search(query).sources, provider.id
        except Exception as e:  # noqa: BLE001 — fall through to the next provider in the chain
            last_error = e
    raise last_error


def _render_markdown(topic: str, angles: list[dict]) -> str:
    lines = [f"# Research: {topic}", ""]
    for a in angles:
        lines.append(f"## {a['angle'].capitalize()}")
        lines.append("")
        lines.append(a["text"])
        lines.append("")
        if a["sources"]:
            lines.append(f"Sources (via `{a['research_provider']}`):")
            for s in a["sources"]:
                lines.append(f"- [{s['title']}]({s['url']}) (confidence: {s['confidence']})")
            lines.append("")
    return "\n".join(lines)
