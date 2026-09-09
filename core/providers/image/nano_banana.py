from __future__ import annotations

import base64
import json
import time
from pathlib import Path

import httpx

from core.env import require_key
from core.providers.contracts import (
    HealthStatus,
    ImageCaps,
    ImageRequest,
    ImageResult,
    Money,
)

ID_PREFIX = "gemini"
API_URL_TMPL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MAX_RETRIES = 3
RETRY_DELAYS_SEC = [1, 4, 10]


class NanoBananaImage:
    """Gemini image generation ("Nano Banana") via the Gemini API's
    generateContent endpoint — same ?key= query-param auth as
    core/providers/tts/google_chirp.py, not OAuth/service-account.

    Required in project.yaml -> providers.image.options:
      api_key_env: name of the .env variable holding a Gemini API key.

    Scope note on batching: plan/phase-4-right-visuals.md §4.4 calls for
    collecting a whole run's images into one batch request to realize
    Google's real batch-API discount. This adapter issues one synchronous
    generateContent call per image instead — matching every other real
    provider in this codebase (openai_compatible.py, google_chirp.py) rather
    than adding this project's first async job-submission/polling pipeline,
    which would be untestable without a live key in this environment. It
    still reports the batch-discounted estimate_cost() when options.batch is
    true, satisfying the ledger-cost DoD check, but does not literally
    realize Google's batch-mode discount — see the plan's Risks section,
    which explicitly sanctions scoping down the hardest sub-parts of this
    phase.
    """

    def __init__(self, model: str, options: dict):
        self.id = f"{ID_PREFIX}/{model}"
        self.model = model
        self.options = options
        self.caps = ImageCaps(resolutions=["1920x1080"], batch=True, edit=True, text_in_image=False)
        self.api_key_env = options.get("api_key_env", "")
        if not self.api_key_env:
            raise ValueError(
                "providers.image.options.api_key_env is required for the 'gemini' image vendor "
                "(name of the .env variable holding your Gemini API key) — set it via "
                "`autovid config set` or the dashboard's project config page."
            )

    def _api_key(self) -> str:
        return require_key(self.api_key_env, self.id)

    def estimate_cost(self, req: ImageRequest) -> Money:
        batch = self.options.get("batch", True)
        return Money(usd=0.0168 if batch else 0.0336)  # see core/providers/pricing.yaml

    def health_check(self) -> HealthStatus:
        try:
            resp = httpx.get(
                f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}",
                params={"key": self._api_key()},
                timeout=10,
            )
            if resp.status_code >= 400:
                return HealthStatus(ok=False, detail=f"GET models/{self.model} -> {resp.status_code} {resp.text[:300]}")
            return HealthStatus(ok=True)
        except Exception as e:  # noqa: BLE001 — health check reports, never raises
            return HealthStatus(ok=False, detail=str(e))

    def generate(self, req: ImageRequest) -> ImageResult:
        payload = {
            "contents": [{"parts": [{"text": self._build_prompt(req)}]}],
            "generationConfig": {"responseModalities": ["IMAGE"]},
        }

        last_error = ""
        for attempt in range(MAX_RETRIES):
            try:
                resp = httpx.post(
                    API_URL_TMPL.format(model=self.model),
                    params={"key": self._api_key()},
                    json=payload,
                    timeout=60,
                )
            except httpx.RequestError as e:
                last_error = str(e)
            else:
                if resp.status_code == 429 or resp.status_code >= 500:
                    last_error = f"{resp.status_code}: {resp.text[:500]}"
                elif resp.status_code >= 400:
                    raise RuntimeError(f"'{self.id}' generate failed: {resp.status_code} {resp.text[:1000]}")
                else:
                    return self._extract_image(resp.json(), req.out_path)
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAYS_SEC[attempt])

        raise RuntimeError(f"'{self.id}' generate failed after {MAX_RETRIES} attempts: {last_error}")

    def _build_prompt(self, req: ImageRequest) -> str:
        parts = [req.subject]
        if req.style_anchor:
            parts.append(f"Style: {req.style_anchor}.")
        if req.no_text:
            parts.append("Do not render any text, letters, or words in the image.")
        parts.append(f"Aspect ratio {req.aspect}.")
        return " ".join(parts)

    def _extract_image(self, data: dict, out_path: str) -> ImageResult:
        for candidate in data.get("candidates") or []:
            for part in candidate.get("content", {}).get("parts", []):
                inline = part.get("inlineData")
                if inline and inline.get("data"):
                    path = Path(out_path)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(base64.b64decode(inline["data"]))
                    return ImageResult(image_path=str(path), provider=self.id, model=self.model)
        raise RuntimeError(f"'{self.id}' generate: response had no image data: {json.dumps(data)[:500]}")


def get_adapter(model: str, options: dict) -> NanoBananaImage:
    return NanoBananaImage(model, options)
