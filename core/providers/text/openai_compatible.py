from __future__ import annotations

import time

import httpx

from core.env import require_key
from core.providers.contracts import HealthStatus, Money, TextRequest, TextResult

ID_PREFIX = "custom"
MAX_RETRIES = 3
RETRY_DELAYS_SEC = [1, 4, 10]


class OpenAICompatibleText:
    """Generic adapter for any OpenAI-compatible /v1/chat/completions endpoint —
    a self-hosted router (e.g. 9router), LiteLLM, vLLM, LM Studio, OpenRouter, etc.

    Nothing about a specific vendor is hardcoded here: point `base_url` at any
    server speaking the OpenAI chat-completions API and pass whatever `model`
    id that server expects (see project.yaml `providers.text` — vendor "custom").

    Required in project.yaml -> providers.text.options:
      base_url:    e.g. http://localhost:20128/v1
      api_key_env: name of the .env variable holding the bearer key — never
                   the raw key itself, so secrets never live in project.yaml.
    """

    def __init__(self, model: str, options: dict):
        self.id = f"{ID_PREFIX}/{model}"
        self.model = model
        self.options = options
        self.base_url = (options.get("base_url") or "").rstrip("/")
        self.api_key_env = options.get("api_key_env", "")
        if not self.base_url:
            raise ValueError(
                "providers.text.options.base_url is required for the 'custom' vendor "
                "(e.g. http://localhost:20128/v1) — set it via `autovid config set` "
                "or the dashboard's project config page."
            )

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key_env:
            key = require_key(self.api_key_env, self.id, config_hint=f"base_url={self.base_url}")
            headers["Authorization"] = f"Bearer {key}"
        return headers

    def estimate_cost(self, req: TextRequest) -> Money:
        # Cost behind a self-hosted router isn't visible to us. If you know the
        # real per-token price, add a "custom/<model>" entry to pricing.yaml —
        # until then this defaults to $0 rather than guessing.
        return Money(usd=0.0)

    def health_check(self) -> HealthStatus:
        try:
            resp = httpx.get(f"{self.base_url}/models", headers=self._headers(), timeout=10)
            if resp.status_code >= 400:
                return HealthStatus(ok=False, detail=f"GET {self.base_url}/models -> {resp.status_code}")
            return HealthStatus(ok=True)
        except Exception as e:  # noqa: BLE001 — health check reports, never raises
            return HealthStatus(ok=False, detail=str(e))

    def generate(self, req: TextRequest) -> TextResult:
        messages = []
        if req.system:
            messages.append({"role": "system", "content": req.system})
        messages.append({"role": "user", "content": req.prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": req.max_output_tokens,
            "temperature": req.temperature,
        }

        last_error = ""
        for attempt in range(MAX_RETRIES):
            try:
                resp = httpx.post(
                    f"{self.base_url}/chat/completions", json=payload, headers=self._headers(), timeout=120
                )
            except httpx.RequestError as e:
                last_error = str(e)
            else:
                if resp.status_code == 429 or resp.status_code >= 500:
                    last_error = f"{resp.status_code}: {resp.text[:500]}"
                elif resp.status_code >= 400:
                    raise RuntimeError(f"'{self.id}' generate failed: {resp.status_code} {resp.text[:1000]}")
                else:
                    data = resp.json()
                    usage = data.get("usage", {})
                    return TextResult(
                        text=data["choices"][0]["message"]["content"],
                        input_tokens=usage.get("prompt_tokens", 0),
                        output_tokens=usage.get("completion_tokens", 0),
                        model=self.model,
                    )
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAYS_SEC[attempt])

        raise RuntimeError(f"'{self.id}' generate failed after {MAX_RETRIES} attempts: {last_error}")


def get_adapter(model: str, options: dict) -> OpenAICompatibleText:
    return OpenAICompatibleText(model, options)
