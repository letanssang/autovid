from __future__ import annotations

import time

import httpx

from core.env import require_key
from core.providers.contracts import (
    HealthStatus,
    Money,
    ResearchQuery,
    ResearchResult,
    ResearchSource,
)
from core.providers.research._shared import confidence_for

ID_PREFIX = "google"
API_URL = "https://www.googleapis.com/customsearch/v1"
MAX_RETRIES = 3
RETRY_DELAYS_SEC = [1, 4, 10]


class GoogleCSEResearch:
    """Google Programmable Search Engine (Custom Search JSON API) — returns
    plain url/title/snippet results, no LLM synthesis (s01_research.py already
    synthesizes separately via the text provider).

    AS OF JANUARY 2026 GOOGLE CLOSED THIS API TO NEW CUSTOMERS
    (see developers.google.com/custom-search/v1/overview). A brand-new GCP
    project will get an unfixable 403 "This project does not have the access
    to Custom Search JSON API" no matter how it's configured — confirmed by
    exhausting every config fix (API enablement, billing link, API key type,
    apikeys.googleapis.com) against a fresh project, all failing identically.
    Only usable if the project already had access before the cutoff; existing
    customers keep it until 2027-01-01, then must move to Vertex AI Search.
    Use duckduckgo_scrape.py instead for a zero-setup free option.

    Required in project.yaml -> providers.research.options:
      cx:          Programmable Search Engine id (not secret — safe in project.yaml),
                   from https://programmablesearchengine.google.com/
      api_key_env: name of the .env variable holding the Google Cloud API key
                   (Custom Search API enabled on that key's project).

    Free up to 100 queries/day; see pricing.yaml for the rate beyond that.
    """

    def __init__(self, model: str, options: dict):
        self.id = f"{ID_PREFIX}/{model}"
        self.model = model
        self.options = options
        self.cx = options.get("cx", "")
        self.api_key_env = options.get("api_key_env", "")
        if not self.cx:
            raise ValueError(
                "providers.research.options.cx is required for the 'google' vendor "
                "(your Programmable Search Engine id) — set it via `autovid config set` "
                "or the dashboard's project config page."
            )

    def _api_key(self) -> str:
        return require_key(self.api_key_env, self.id, config_hint=f"cx={self.cx}")

    def estimate_cost(self, req: ResearchQuery) -> Money:
        # Free for the first 100 queries/day; see pricing.yaml for the $5/1k rate beyond that.
        return Money(usd=0.0)

    def health_check(self) -> HealthStatus:
        try:
            resp = httpx.get(
                API_URL, params={"key": self._api_key(), "cx": self.cx, "q": "test", "num": 1}, timeout=10
            )
            if resp.status_code >= 400:
                return HealthStatus(ok=False, detail=f"GET {API_URL} -> {resp.status_code} {resp.text[:300]}")
            return HealthStatus(ok=True)
        except Exception as e:  # noqa: BLE001 — health check reports, never raises
            return HealthStatus(ok=False, detail=str(e))

    def search(self, req: ResearchQuery) -> ResearchResult:
        params = {
            "key": self._api_key(),
            "cx": self.cx,
            "q": req.query,
            "num": max(1, min(req.max_results, 10)),
        }

        last_error = ""
        for attempt in range(MAX_RETRIES):
            try:
                resp = httpx.get(API_URL, params=params, timeout=30)
            except httpx.RequestError as e:
                last_error = str(e)
            else:
                if resp.status_code == 429 or resp.status_code >= 500:
                    last_error = f"{resp.status_code}: {resp.text[:500]}"
                elif resp.status_code >= 400:
                    raise RuntimeError(f"'{self.id}' search failed: {resp.status_code} {resp.text[:1000]}")
                else:
                    items = resp.json().get("items", [])
                    sources = [
                        ResearchSource(
                            url=item["link"],
                            title=item.get("title", ""),
                            snippet=item.get("snippet", ""),
                            confidence=confidence_for(item["link"]),
                        )
                        for item in items
                    ]
                    return ResearchResult(sources=sources)
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAYS_SEC[attempt])

        raise RuntimeError(f"'{self.id}' search failed after {MAX_RETRIES} attempts: {last_error}")


def get_adapter(model: str, options: dict) -> GoogleCSEResearch:
    return GoogleCSEResearch(model, options)
