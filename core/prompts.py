from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def render_prompt(locale: str, fmt: str, name: str, **context) -> str:
    """Renders prompts/<locale>/<fmt>/<name>.md — prompts never live in Python f-strings.

    `fmt` is the video format (e.g. "educational"). New formats (narrative, listicle,
    review, ...) are added as sibling directories under prompts/<locale>/ without
    touching stage code — see project.yaml's top-level `format` field.
    """
    env = Environment(loader=FileSystemLoader(str(PROMPTS_DIR / locale / fmt)))
    template = env.get_template(f"{name}.md")
    return template.render(**context)


def parse_json_response(text: str) -> Any:
    """Best-effort JSON parse of an LLM's raw text response.

    Models routinely wrap JSON in a ```json fence, or add leading/trailing
    prose ("Here's the JSON:"). Tries, in order: a fenced block, the raw text
    as-is, then the outermost {...}/[...] span. Raises ValueError (callers
    should fall back to a safe default, per plan/phase-1-real-content.md's
    "đừng tin output LLM là hợp lệ") rather than letting a malformed response
    take down the whole stage.
    """
    candidates = []
    fence_match = _FENCE_RE.search(text)
    if fence_match:
        candidates.append(fence_match.group(1))
    candidates.append(text.strip())

    start_obj, start_arr = text.find("{"), text.find("[")
    starts = [p for p in (start_obj, start_arr) if p != -1]
    if starts:
        start = min(starts)
        end_obj, end_arr = text.rfind("}"), text.rfind("]")
        end = max(end_obj, end_arr)
        if end > start:
            candidates.append(text[start : end + 1])

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
    raise ValueError(f"Could not parse JSON from LLM response: {text[:200]!r}")
