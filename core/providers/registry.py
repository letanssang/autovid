from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import yaml

from core.budget import BudgetTracker
from core.providers import pricing

CAPABILITY_PACKAGES = {
    "text": "core.providers.text",
    "research": "core.providers.research",
    "tts": "core.providers.tts",
    "image": "core.providers.image",
    "video_clip": "core.providers.video_clip",
    "slides": "core.providers.slides",
    "publish": "core.providers.publish",
}

# project.yaml addresses providers as "<vendor>/<model>" (e.g. "google/chirp3-hd").
# Vendor names are stable config identifiers; module filenames are an
# implementation detail that can change without breaking a project's config.
VENDOR_MODULES = {
    "text": {
        "gemini": "gemini", "anthropic": "claude", "openai": "openai", "ollama": "ollama",
        "custom": "openai_compatible",  # any OpenAI-compatible endpoint — see providers.text.options.base_url
        "local": "local_fake",
    },
    "research": {
        "gemini": "gemini_grounding", "tavily": "tavily", "exa": "exa",
        "google": "google_cse",  # Google Custom Search JSON API — see providers.research.options.cx
        "duckduckgo": "duckduckgo_scrape",  # free unofficial scrape — fallback use only, see module docstring
        "local": "local_fake",
    },
    "tts": {"google": "google_chirp", "elevenlabs": "elevenlabs", "piper": "piper", "edge": "edge", "local": "local_fake"},
    "image": {"gemini": "nano_banana", "google": "imagen", "flux": "flux", "sdxl": "sdxl_local", "manual": "manual"},
    "video_clip": {"veo": "veo", "kling": "kling"},
    "slides": {"local": "html_renderer", "notebooklm": "notebooklm"},
    "publish": {"youtube": "youtube", "local": "local_only"},
}

# Capabilities with a per-call cost, metered against project.yaml's budget.cap_usd.
# slides and publish are locally-executed / free, so they aren't metered.
METERED_CAPABILITIES = {
    "text": "generate",
    "research": "search",
    "tts": "synthesize",
    "image": "generate",
    "video_clip": "generate",
}


class BudgetExceeded(Exception):
    pass


class _MeteredAdapter:
    """Wraps an adapter so its metered method is cost-tracked against the project budget."""

    def __init__(self, adapter: Any, capability: str, budget: BudgetTracker):
        self._adapter = adapter
        self._capability = capability
        self._budget = budget
        setattr(self, METERED_CAPABILITIES[capability], self._metered_call)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._adapter, name)

    def _metered_call(self, req: Any) -> Any:
        if self._budget.check() == "stop":
            raise BudgetExceeded(f"'{self._capability}' budget cap reached (${self._budget.cap_usd:.2f})")
        estimated = self._adapter.estimate_cost(req)
        result = getattr(self._adapter, METERED_CAPABILITIES[self._capability])(req)
        real_cost = self._real_cost(result, estimated.usd)
        self._budget.record(
            self._capability, self._adapter.id, real_cost, estimated_usd=estimated.usd, usage=self._usage(result)
        )
        return result

    def _real_cost(self, result: Any, estimated_usd: float) -> float:
        """Recompute cost from the call's real usage when we can — token counts for text
        calls, real char_count for TTS, pricing.yaml for the rate — falling back to the
        pre-call estimate otherwise (e.g. an opaque self-hosted router where no per-token
        price is known)."""
        input_tokens = getattr(result, "input_tokens", None)
        output_tokens = getattr(result, "output_tokens", None)
        if input_tokens is not None and output_tokens is not None:
            real = pricing.text_cost_usd(self._adapter.id, input_tokens, output_tokens)
            if real is not None:
                return real
        char_count = getattr(result, "char_count", None)
        if char_count is not None:
            real = pricing.tts_cost_usd(self._adapter.id, char_count)
            if real is not None:
                return real
        return estimated_usd

    def _usage(self, result: Any) -> dict | None:
        """Real per-call usage worth keeping in the ledger for later auditing
        (Phase 7) even when cost is $0 — e.g. char_count for a free TTS provider."""
        char_count = getattr(result, "char_count", None)
        if char_count is not None:
            return {"char_count": char_count}
        input_tokens = getattr(result, "input_tokens", None)
        output_tokens = getattr(result, "output_tokens", None)
        if input_tokens is not None and output_tokens is not None:
            return {"input_tokens": input_tokens, "output_tokens": output_tokens}
        return None


class Registry:
    """Resolves capability -> adapter instance from project.yaml, with per-stage routing and cost metering."""

    def __init__(self, providers_config: dict[str, Any], budget: BudgetTracker | None = None):
        self.config = providers_config
        self.budget = budget

    def _route_for(self, capability: str, stage: str | None) -> str | None:
        cap_cfg = self.config.get(capability) or {}
        routes = cap_cfg.get("routes") or {}
        if stage and stage in routes:
            return routes[stage]
        return cap_cfg.get("default")

    def options(self, capability: str) -> dict:
        return (self.config.get(capability) or {}).get("options", {}) or {}

    def fallback_chain(self, capability: str) -> list[str]:
        return (self.config.get(capability) or {}).get("fallback", []) or []

    def resolve(self, capability: str, stage: str | None = None) -> Any:
        """Returns an adapter instance, or None if the capability is disabled (default: null)."""
        provider_id = self._route_for(capability, stage)
        if not provider_id:
            return None
        return self.resolve_provider(capability, provider_id)

    def resolve_provider(self, capability: str, provider_id: str) -> Any:
        """Like resolve(), but for an explicit '<vendor>/<model>' id instead of
        routing through project.yaml — used to walk a capability's fallback chain."""
        adapter = self._load_adapter(capability, provider_id)
        if self.budget and capability in METERED_CAPABILITIES:
            return _MeteredAdapter(adapter, capability, self.budget)
        return adapter

    def _load_adapter(self, capability: str, provider_id: str) -> Any:
        vendor, _, model = provider_id.partition("/")
        module_name = VENDOR_MODULES[capability].get(vendor)
        if module_name is None:
            raise ValueError(f"Unknown {capability} vendor '{vendor}' in provider id '{provider_id}'")
        module = importlib.import_module(f"{CAPABILITY_PACKAGES[capability]}.{module_name}")
        return module.get_adapter(model, self.options(capability))

    @classmethod
    def from_project_yaml(cls, project_root: Path) -> Registry:
        config = yaml.safe_load((project_root / "project.yaml").read_text())
        cap_usd = (config.get("budget") or {}).get("cap_usd", 1.0)
        budget = BudgetTracker(project_root=project_root, cap_usd=cap_usd)
        budget.load()
        return cls(config.get("providers", {}), budget=budget)
