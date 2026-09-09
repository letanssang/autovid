from __future__ import annotations

from urllib.parse import urlparse

# Confidence-scoring convention (printed into research.md for human review):
#   .gov / .edu / .int domains         -> 0.9  (primary/authoritative)
#   known major news outlets           -> 0.7
#   other .org domains                 -> 0.6  (mixed — NGOs, standards bodies, wikis)
#   everything else (blogs, forums...) -> 0.4
_MAJOR_NEWS_DOMAINS = {
    "reuters.com", "apnews.com", "bbc.co.uk", "bbc.com", "npr.org",
    "nytimes.com", "wsj.com", "theguardian.com", "bloomberg.com", "nature.com",
    "sciencedirect.com", "sciencemag.org",
}


def confidence_for(url: str) -> float:
    domain = urlparse(url).netloc.lower().removeprefix("www.")
    if domain.endswith((".gov", ".edu", ".int")):
        return 0.9
    if domain in _MAJOR_NEWS_DOMAINS:
        return 0.7
    if domain.endswith(".org"):
        return 0.6
    return 0.4
