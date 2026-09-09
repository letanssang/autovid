from __future__ import annotations

import json
from pathlib import Path

from core.prompts import render_prompt
from core.providers.contracts import TextRequest
from core.providers.registry import Registry
from core.state import ProjectState

STAGE = "05_assets"
PROMPTS_SUBDIR = "manual_prompts"
IMAGES_SUBDIR = "images"
PENDING_MANIFEST = "manual_pending.json"
ASSETS_MANIFEST = "assets_manifest.json"


# ---- path convention: single source of truth for the provider, the stage,
# ---- and the dashboard, so they can never disagree on where a file lives.

def image_prompt_path(project_root: Path, beat_id: str) -> Path:
    return project_root / STAGE / PROMPTS_SUBDIR / f"{beat_id}.md"


def expected_image_path(project_root: Path, beat_id: str) -> Path:
    return project_root / STAGE / IMAGES_SUBDIR / f"{beat_id}.png"


def _pending_manifest_path(project_root: Path) -> Path:
    return project_root / STAGE / PENDING_MANIFEST


def _assets_manifest_path(project_root: Path) -> Path:
    return project_root / STAGE / ASSETS_MANIFEST


# ---- read/list ----

def list_pending(project_root: Path) -> list[dict]:
    path = _pending_manifest_path(project_root)
    if not path.exists():
        return []
    return json.loads(path.read_text()).get("pending", [])


def _get_pending(project_root: Path, beat_id: str) -> dict:
    match = next((p for p in list_pending(project_root) if p["beat_id"] == beat_id), None)
    if match is None:
        raise ValueError(f"'{beat_id}' is not a pending manual image asset for this project")
    return match


def read_prompt(project_root: Path, beat_id: str) -> str:
    _get_pending(project_root, beat_id)
    return image_prompt_path(project_root, beat_id).read_text()


# ---- write: direct hand-edit path ----

def write_prompt(project_root: Path, beat_id: str, text: str) -> None:
    _get_pending(project_root, beat_id)
    image_prompt_path(project_root, beat_id).write_text(text)


# ---- write: LLM-assisted rewrite path ----

def improve_prompt(project_root: Path, beat_id: str, instruction: str) -> str:
    """Rewrites this beat's prompt via the project's configured 'text' capability,
    per a free-text instruction. Plain-text response (not JSON) — the desired
    output IS the raw prompt string. May raise registry.BudgetExceeded if the
    text provider is metered and the project's budget cap is already spent."""
    _get_pending(project_root, beat_id)
    current = read_prompt(project_root, beat_id)

    config = ProjectState(root=project_root).load_config()
    locale = config.get("locales", ["en"])[0]
    fmt = config.get("format", "educational")
    registry = Registry.from_project_yaml(project_root)
    text_provider = registry.resolve("text", stage=STAGE)

    prompt = render_prompt(locale, fmt, "improve_image_prompt", current_prompt=current, instruction=instruction)
    result = text_provider.generate(TextRequest(prompt=prompt, stage=STAGE))
    new_text = _strip_fence(result.text)
    write_prompt(project_root, beat_id, new_text)
    return new_text


def _strip_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:-1] if lines and lines[-1].strip() == "```" else lines[1:]
        text = "\n".join(lines).strip()
    return text


# ---- import a finished asset — closes the loop ----

def import_asset(project_root: Path, beat_id: str, data: bytes) -> Path:
    """Writes `data` (bytes of a user-supplied finished PNG) to this beat's
    expected path, then patches assets_manifest.json + removes the beat from
    manual_pending.json — so a plain `autovid run <project>` can continue
    straight to 06_render without re-running TTS/slides for every other beat."""
    _get_pending(project_root, beat_id)
    if not data:
        raise ValueError("uploaded file is empty")

    dest = expected_image_path(project_root, beat_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)

    _patch_assets_manifest(project_root, beat_id, str(dest))
    _remove_pending(project_root, beat_id)
    return dest


def _patch_assets_manifest(project_root: Path, beat_id: str, asset_path: str) -> None:
    path = _assets_manifest_path(project_root)
    manifest = json.loads(path.read_text())
    manifest["visuals"] = [v for v in manifest["visuals"] if v["beat_id"] != beat_id]
    manifest["visuals"].append({"beat_id": beat_id, "type": "ai_image", "asset_path": asset_path})
    path.write_text(json.dumps(manifest, indent=2))


def _remove_pending(project_root: Path, beat_id: str) -> None:
    path = _pending_manifest_path(project_root)
    pending = [p for p in list_pending(project_root) if p["beat_id"] != beat_id]
    path.write_text(json.dumps({"pending": pending}, indent=2))
