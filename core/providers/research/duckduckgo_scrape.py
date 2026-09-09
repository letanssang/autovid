from __future__ import annotations

import html
import re
import time
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from core.providers.contracts import (
    HealthStatus,
    Money,
    ResearchQuery,
    ResearchResult,
    ResearchSource,
)
from core.providers.research._shared import confidence_for

ID_PREFIX = "duckduckgo"
HTML_URL = "https://html.duckduckgo.com/html/"
MAX_RETRIES = 3
RETRY_DELAYS_SEC = [1, 4, 10]

# Scrapes DuckDuckGo's no-JS HTML results page — no API key, no official
# terms-of-service coverage, and it can break silently if DDG changes markup.
# Meant as a free fallback (providers.research.fallback) behind a real API
# provider (google/custom_search, tavily/search), not as a primary choice.
_RESULT_RE = re.compile(
    r'result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?result__snippet[^>]*>(.*?)</a>',
    re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")


def _clean(text: str) -> str:
    return html.unescape(_TAG_RE.sub("", text)).strip()


def _resolve_url(href: str) -> str:
    if href.startswith("//"):
        href = f"https:{href}"
    parsed = urlparse(href)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path == "/l/":
        real = parse_qs(parsed.query).get("uddg", [""])[0]
        return unquote(real) or href
    return href


class DuckDuckGoScrapeResearch:
    def __init__(self, model: str, options: dict):
        self.id = f"{ID_PREFIX}/{model}"
        self.model = model
        self.options = options

    def estimate_cost(self, req: ResearchQuery) -> Money:
        return Money(usd=0.0)

    def health_check(self) -> HealthStatus:
        try:
            resp = httpx.get(HTML_URL, params={"q": "test"}, timeout=10)
            if resp.status_code >= 400:
                return HealthStatus(ok=False, detail=f"GET {HTML_URL} -> {resp.status_code}")
            return HealthStatus(ok=True, detail="unofficial scrape — no ToS coverage, can break without notice")
        except Exception as e:  # noqa: BLE001 — health check reports, never raises
            return HealthStatus(ok=False, detail=str(e))

    def search(self, req: ResearchQuery) -> ResearchResult:
        last_error = ""
        for attempt in range(MAX_RETRIES):
            try:
                resp = httpx.get(
                    HTML_URL,
                    params={"q": req.query},
                    headers={"User-Agent": "Mozilla/5.0 (compatible; AutoVid research fallback)"},
                    timeout=30,
                )
            except httpx.RequestError as e:
                last_error = str(e)
            else:
                if resp.status_code == 429 or resp.status_code >= 500:
                    last_error = f"{resp.status_code}: {resp.text[:500]}"
                elif resp.status_code >= 400:
                    raise RuntimeError(f"'{self.id}' search failed: {resp.status_code} {resp.text[:1000]}")
                else:
                    sources = []
                    for href, title, snippet in _RESULT_RE.findall(resp.text)[: req.max_results]:
                        url = _resolve_url(href)
                        sources.append(
                            ResearchSource(
                                url=url,
                                title=_clean(title),
                                snippet=_clean(snippet),
                                confidence=confidence_for(url),
                            )
                        )
                    return ResearchResult(sources=sources)
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAYS_SEC[attempt])

        raise RuntimeError(f"'{self.id}' search failed after {MAX_RETRIES} attempts: {last_error}")


def get_adapter(model: str, options: dict) -> DuckDuckGoScrapeResearch:
    return DuckDuckGoScrapeResearch(model, options)
