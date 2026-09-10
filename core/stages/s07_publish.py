from __future__ import annotations

import json
import shutil
from pathlib import Path

from core.prompts import parse_json_response, render_prompt
from core.providers.contracts import (
    ImageRequest,
    PublishRequest,
    SlideRequest,
    TextRequest,
)
from core.providers.registry import Registry

STAGE = "07_publish"

THUMBNAIL_SIZE = "1280x720"
THUMBNAIL_VARIANTS = ("a", "b", "c")
MAX_SOURCES = 10


def run(project_root: Path, config: dict) -> None:
    topic = config.get("topic", "")
    locale = config.get("locales", ["en"])[0]
    fmt = config.get("format", "educational")
    registry = Registry.from_project_yaml(project_root)
    text_provider = registry.resolve("text", stage=STAGE)
    slides_provider = registry.resolve("slides", stage=STAGE)
    image_provider = registry.resolve("image", stage=STAGE)
    style_anchor = registry.options("image").get("style_anchor", "")
    publish_provider = registry.resolve("publish", stage=STAGE)

    out_dir = project_root / STAGE
    out_dir.mkdir(parents=True, exist_ok=True)

    outline = json.loads((project_root / "02_outline" / "outline.json").read_text())
    research = json.loads((project_root / "01_research" / "research.json").read_text())
    render_manifest_path = project_root / "06_render" / "render_manifest.json"
    render_manifest = (
        json.loads(render_manifest_path.read_text()) if render_manifest_path.exists() else {"timeline": []}
    )
    hook_text = next((e["text"] for e in render_manifest["timeline"] if e["section_id"] == "hook"), topic)

    # ---- 6.1: thumbnail — one shared background, 3 cheap text variants ----
    background_uri = _select_thumbnail_background(render_manifest, image_provider, style_anchor, topic, out_dir)
    texts = _generate_thumbnail_texts(text_provider, locale, fmt, topic, hook_text)

    thumbnail_path = out_dir / "thumbnail.png"
    if slides_provider is not None:
        for letter, text in zip(THUMBNAIL_VARIANTS, texts):
            variant_path = out_dir / f"thumbnail_{letter}.png"
            slides_provider.render(SlideRequest(
                template="thumbnail",
                content={"text": text, "background_uri": background_uri, "font_size_px": _thumbnail_font_size(text)},
                out_path=str(variant_path),
                locale=locale,
                size=THUMBNAIL_SIZE,
            ))
        canonical_variant = out_dir / f"thumbnail_{THUMBNAIL_VARIANTS[0]}.png"
        if canonical_variant.exists() and canonical_variant.stat().st_size > 0:
            shutil.copy(canonical_variant, thumbnail_path)
    if not thumbnail_path.exists():
        thumbnail_path.write_bytes(b"")

    # ---- 6.2: metadata — LLM title/description/tags + computed chapters/sources ----
    outline_summary = "\n".join(
        f"- {ch['chapter_title']}: " + ", ".join(s["title"] for s in ch["sections"])
        for ch in outline["chapters"]
    )
    sources = _collect_sources(research)
    sources_summary = "\n".join(f"- {title} ({url})" for title, url in sources) or "(no sources recorded)"

    generated = _generate_metadata(text_provider, locale, fmt, topic, outline_summary, sources_summary)
    chapters = _compute_chapters(outline, render_manifest)

    description_parts = [generated["description"]]
    if chapters:
        description_parts.append("Chapters:\n" + "\n".join(f"{_yt_timestamp(s)} {t}" for s, t in chapters))
    if sources:
        description_parts.append("Sources:\n" + "\n".join(f"- {title}: {url}" for title, url in sources))
    description_parts.append("Generated with AutoVid.")

    publish_options = (config.get("providers", {}).get("publish", {}) or {}).get("options", {}) or {}
    metadata = {
        "title": generated["title"],
        "description": "\n\n".join(description_parts),
        "tags": generated["tags"],
        "privacy": publish_options.get("privacy", "private"),
    }
    (out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

    if publish_provider is None:
        return

    video_path = project_root / "06_render" / "output.mp4"
    publish_provider.publish(PublishRequest(
        video_path=str(video_path), title=metadata["title"], description=metadata["description"],
        tags=metadata["tags"], thumbnail_path=str(thumbnail_path), privacy=metadata["privacy"],
    ))


def _select_thumbnail_background(
    render_manifest: dict, image_provider, style_anchor: str, topic: str, out_dir: Path
) -> str:
    """Tier 1: reuse the first valid rendered beat asset (near-free, and
    visually consistent with the video itself — by construction the timeline
    starts with the hook section). Tier 2: if that's unavailable and an image
    provider is configured, generate one fresh hero image. Tier 3 (caller):
    an empty string falls back to a plain CSS gradient in the template.

    Tier 2 is deliberately best-effort — any failure (including
    ManualAssetPending or BudgetExceeded) just falls through to the gradient,
    because by this point output.mp4 already exists and 07_publish must not
    abort the whole stage over an optional thumbnail background.
    """
    for entry in render_manifest["timeline"]:
        asset_path = entry.get("asset_path")
        if asset_path and Path(asset_path).exists() and Path(asset_path).stat().st_size > 0:
            return Path(asset_path).resolve().as_uri()

    if image_provider is not None:
        hero_path = out_dir / "thumbnail_background.png"
        try:
            result = image_provider.generate(ImageRequest(
                intent="hero", subject=topic, maps_to=topic, style_anchor=style_anchor,
                out_path=str(hero_path), aspect="16:9",
            ))
            if Path(result.image_path).exists() and Path(result.image_path).stat().st_size > 0:
                return Path(result.image_path).resolve().as_uri()
        except Exception:  # noqa: BLE001, S110 — best-effort fallback, see docstring
            pass

    return ""


def _thumbnail_font_size(text: str) -> int:
    length = len(text)
    if length <= 20:
        return 128
    if length <= 35:
        return 100
    if length <= 50:
        return 80
    return 64


def _generate_thumbnail_texts(text_provider, locale: str, fmt: str, topic: str, hook_text: str) -> list[str]:
    prompt = render_prompt(locale, fmt, "thumbnail_text", topic=topic, hook_text=hook_text)
    result = text_provider.generate(TextRequest(prompt=prompt, stage=STAGE))
    try:
        parsed = parse_json_response(result.text)
        variants = [str(v).strip() for v in parsed if str(v).strip()]
        if not variants:
            raise ValueError("empty variant list")
    except (ValueError, AttributeError, TypeError):
        variants = [topic]
    while len(variants) < len(THUMBNAIL_VARIANTS):
        variants.append(variants[-1])
    return variants[: len(THUMBNAIL_VARIANTS)]


def _generate_metadata(
    text_provider, locale: str, fmt: str, topic: str, outline_summary: str, sources_summary: str
) -> dict:
    prompt = render_prompt(locale, fmt, "metadata", topic=topic, outline_summary=outline_summary, sources_summary=sources_summary)
    result = text_provider.generate(TextRequest(prompt=prompt, stage=STAGE))
    try:
        parsed = parse_json_response(result.text)
        title = str(parsed.get("title", "")).strip()
        description = str(parsed.get("description", "")).strip()
        tags = [str(t).strip() for t in parsed.get("tags", []) if str(t).strip()]
        if not title or not description or not tags:
            raise ValueError("missing required metadata field")
    except (ValueError, AttributeError, TypeError, KeyError):
        title = topic
        description = f"An educational video about {topic}."
        tags = [t.strip() for t in topic.split() if t.strip()][:15]

    return {
        "title": title[:70],
        "description": description,
        "tags": list(dict.fromkeys(tags))[:15],
    }


def _collect_sources(research: dict, limit: int = MAX_SOURCES) -> list[tuple[str, str]]:
    seen: set[str] = set()
    sources: list[tuple[str, str]] = []
    for angle in research.get("angles", []):
        for s in angle.get("sources", []):
            url = s.get("url", "")
            if not url or url in seen:
                continue
            seen.add(url)
            sources.append((s.get("title", url), url))
            if len(sources) >= limit:
                return sources
    return sources


def _compute_chapters(outline: dict, render_manifest: dict) -> list[tuple[float, str]]:
    section_start: dict[str, float] = {}
    for entry in render_manifest["timeline"]:
        sid = entry["section_id"]
        if sid not in section_start:
            section_start[sid] = entry["start_sec"]

    chapters: list[tuple[float, str]] = []
    if "hook" in section_start:
        chapters.append((section_start["hook"], "Introduction"))
    for ch in outline["chapters"]:
        first_section = ch["sections"][0] if ch["sections"] else None
        if first_section and first_section["id"] in section_start:
            chapters.append((section_start[first_section["id"]], ch["chapter_title"]))
    if "outro" in section_start:
        chapters.append((section_start["outro"], "Conclusion"))

    # Force strictly-ascending timestamps starting at exactly 0:00 — required
    # for YouTube to display chapters at all. Not a general ≥10s-spacing
    # validator (plan/phase-6-publish-package.md §6.2 judged that
    # over-engineering); this is just enough to guarantee validity.
    fixed: list[tuple[float, str]] = []
    last = -1.0
    for start, title in chapters:
        if start <= last:
            start = last + 1.0
        fixed.append((start, title))
        last = start
    if fixed:
        fixed[0] = (0.0, fixed[0][1])
    return fixed


def _yt_timestamp(seconds: float) -> str:
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
