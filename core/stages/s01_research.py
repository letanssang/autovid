from __future__ import annotations

import json
from pathlib import Path

from core.prompts import render_prompt
from core.providers.contracts import ResearchQuery, TextRequest
from core.providers.registry import Registry

STAGE = "01_research"

# Fixed angle set for the educational format. Kept here (not in a prompt file)
# because it also drives 02_outline's chapter structure.
RESEARCH_ANGLES = [
    "overview",
    "how it works",
    "why it matters",
    "common misconceptions",
    "practical examples",
]


def slug(text: str) -> str:
    return text.lower().replace(" ", "-")


def run(project_root: Path, config: dict) -> None:
    topic = config["topic"]
    locale = config.get("locales", ["en"])[0]
    fmt = config.get("format", "educational")
    registry = Registry.from_project_yaml(project_root)

    research_chain = _research_chain(registry)
    text_provider = registry.resolve("text", stage=STAGE)

    angles = []
    for angle in RESEARCH_ANGLES:
        sources, provider_used = _search_with_fallback(research_chain, ResearchQuery(query=f"{topic} {angle}"))
        prompt = render_prompt(locale, fmt, "research", topic=topic, angle=angle)
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
