from __future__ import annotations

from pathlib import Path

from core.providers.contracts import (
    HealthStatus,
    ImageCaps,
    ImageRequest,
    ImageResult,
    ManualAssetPending,
    Money,
)

ID_PREFIX = "manual"


class ManualImage:
    """Human-in-the-loop image "generation": writes a prompt to disk and waits
    for a human to create the image with any free tool and feed it back via
    core.manual_assets.import_asset (surfaced through the dashboard's
    manual-assets page). $0 cost, no API key.

    s05_assets.py always writes ImageRequest.out_path as
    <project_root>/05_assets/images/<beat_id>.png — beat_id and project_root
    are derived from that path rather than adding a field to the shared
    ImageRequest contract used by every other image vendor.
    """

    def __init__(self, model: str, options: dict):
        self.id = f"{ID_PREFIX}/{model}"
        self.model = model
        self.options = options
        self.caps = ImageCaps(resolutions=["1920x1080"], batch=False, edit=False, text_in_image=False)

    def estimate_cost(self, req: ImageRequest) -> Money:
        return Money(usd=0.0)

    def health_check(self) -> HealthStatus:
        return HealthStatus(ok=True, detail="manual provider — no external service to check")

    def generate(self, req: ImageRequest) -> ImageResult:
        out_path = Path(req.out_path)
        if out_path.exists():
            return ImageResult(image_path=str(out_path), provider=self.id, model=self.model)

        from core.manual_assets import (
            image_prompt_path,  # local import — avoid a core.manual_assets <-> providers cycle
        )

        beat_id = out_path.stem
        project_root = out_path.parent.parent.parent
        prompt_path = image_prompt_path(project_root, beat_id)
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(self._build_prompt(req))

        raise ManualAssetPending(
            beat_id=beat_id, prompt_path=str(prompt_path), expected_path=str(out_path), capability="image"
        )

    def _build_prompt(self, req: ImageRequest) -> str:
        parts = [req.subject]
        if req.style_anchor:
            parts.append(f"Style: {req.style_anchor}.")
        if req.no_text:
            parts.append("Do not render any text, letters, or words in the image.")
        parts.append(f"Aspect ratio {req.aspect}.")
        return " ".join(parts)


def get_adapter(model: str, options: dict) -> ManualImage:
    return ManualImage(model, options)
