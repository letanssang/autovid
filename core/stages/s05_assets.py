from __future__ import annotations

import json
from pathlib import Path

from core.providers.contracts import (
    ImageRequest,
    ManualAssetPending,
    SlideRequest,
    TTSRequest,
    TTSResult,
)
from core.providers.registry import Registry

STAGE = "05_assets"

SLIDE_TEMPLATES = {"title", "diagram", "code", "comparison", "quote"}


def run(project_root: Path, config: dict) -> None:
    locale = config.get("locales", ["en"])[0]
    registry = Registry.from_project_yaml(project_root)
    tts_options = registry.options("tts")
    tts_chain = _tts_chain(registry)
    slides_provider = registry.resolve("slides", stage=STAGE)
    image_provider = registry.resolve("image", stage=STAGE)
    image_options = registry.options("image")
    style_anchor = image_options.get("style_anchor", "")

    script = json.loads((project_root / "03_script" / "script.json").read_text())
    visual_plan = json.loads((project_root / "04_visual_plan" / "visual_plan.json").read_text())

    out_dir = project_root / STAGE
    audio_dir = out_dir / "audio"
    images_dir = out_dir / "images"
    slides_dir = out_dir / "slides"
    for d in (audio_dir, images_dir, slides_dir):
        d.mkdir(parents=True, exist_ok=True)

    audio_manifest = []
    for section in script["sections"]:
        out_path = audio_dir / f"{section['id']}.mp3"
        result, provider_used = _synthesize_with_fallback(tts_chain, TTSRequest(
            text=section["script"],
            out_path=str(out_path),
            locale=locale,
            voice_id=tts_options.get("voice", ""),
            rate=tts_options.get("rate", 1.0),
        ))
        audio_manifest.append({
            "section_id": section["id"],
            "audio_path": result.audio_path,
            "duration_sec": result.duration_sec,
            "char_count": result.char_count,
            "tts_provider": provider_used,
        })

    visual_manifest = []
    degraded_slides = []
    manual_pending = []
    for beat in visual_plan["beats"]:
        beat_id = f"{beat['section_id']}-{beat['beat_index']}"
        vtype = beat["visual_type"]

        if vtype == "ai_image" and image_provider is None:
            vtype = "b_roll"

        if vtype == "ai_image":
            out_path = images_dir / f"{beat_id}.png"
            try:
                result = image_provider.generate(ImageRequest(
                    intent="metaphor",
                    subject=beat["text"],
                    maps_to=beat["text"],
                    style_anchor=style_anchor,
                    out_path=str(out_path),
                ))
            except ManualAssetPending as e:
                manual_pending.append({
                    "beat_id": e.beat_id,
                    "prompt_path": e.prompt_path,
                    "expected_path": e.expected_path,
                    "text": beat["text"],
                })
                continue
            visual_manifest.append({"beat_id": beat_id, "type": "ai_image", "asset_path": result.image_path})
        else:
            # Every beat on the timeline must resolve to a real asset (plan/phase-3
            # §3.2), never `None`, or audio/video drift accumulates in s06_render.
            # b_roll renders as a "quote" slide pulled from the beat's own
            # narration (plan/phase-4-right-visuals.md §4.3 — $0 cost, no
            # copyright risk, unlike a stock-image library or spending the
            # ai_image budget on what's usually the most common type).
            template = "quote" if vtype == "b_roll" else (vtype if vtype in SLIDE_TEMPLATES else "title")
            content = beat.get("slide_content") or {"title": beat["text"]}
            out_path = slides_dir / f"{beat_id}.png"
            result = slides_provider.render(SlideRequest(
                template=template, content=content, out_path=str(out_path), locale=locale,
            ))
            visual_manifest.append({"beat_id": beat_id, "type": vtype, "asset_path": result.image_path})
            if not result.ok:
                degraded_slides.append({"beat_id": beat_id, "template": template, "error": result.error})

    (out_dir / "assets_manifest.json").write_text(json.dumps({
        "audio": audio_manifest,
        "visuals": visual_manifest,
    }, indent=2))
    (out_dir / "slide_render_status.json").write_text(json.dumps({"degraded": degraded_slides}, indent=2))
    (out_dir / "manual_pending.json").write_text(json.dumps({"pending": manual_pending}, indent=2))


def _tts_chain(registry: Registry) -> list:
    """Primary tts provider plus its configured fallback chain (project.yaml
    providers.tts.fallback), each resolved and cost-metered like the primary.
    Matters most for edge/tts: an unofficial API that can break without notice
    (see plan/phase-2-real-voice.md risk section)."""
    primary = registry.resolve("tts", stage=STAGE)
    fallbacks = [registry.resolve_provider("tts", pid) for pid in registry.fallback_chain("tts")]
    return [p for p in [primary, *fallbacks] if p is not None]


def _synthesize_with_fallback(chain: list, req: TTSRequest) -> tuple[TTSResult, str]:
    """Try each provider in the chain in order; return the first one that
    succeeds, tagged with its id so assets_manifest.json shows what actually
    served it."""
    if not chain:
        raise ValueError("No tts provider configured — see project.yaml providers.tts")
    last_error: Exception | None = None
    for provider in chain:
        try:
            return provider.synthesize(req), provider.id
        except Exception as e:  # noqa: BLE001 — fall through to the next provider in the chain
            last_error = e
    raise last_error
