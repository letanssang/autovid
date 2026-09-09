from __future__ import annotations

import re

_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+")


def split_into_sentence_chunks(text: str, max_chars: int) -> list[str]:
    """Split text into chunks no larger than max_chars, breaking only at sentence
    boundaries — a chunk seam mid-sentence is audible as a splice once the
    chunks are synthesized separately and joined back together (see
    plan/phase-2-real-voice.md §2.1). A single sentence longer than max_chars
    is kept whole rather than cut mid-word."""
    sentences = [s for s in _SENTENCE_END_RE.split(text.strip()) if s]
    if not sentences:
        return []

    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip() if current else sentence
        if current and len(candidate) > max_chars:
            chunks.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks
