from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import edge_tts

from core.audio import (
    FFmpegNotFound,
    concat_audio,
    normalize_loudness,
    probe_duration_sec,
    require_ffmpeg_tools,
)
from core.providers.contracts import HealthStatus, Money, TTSRequest, TTSResult
from core.providers.tts._shared import split_into_sentence_chunks

ID_PREFIX = "edge"
DEFAULT_VOICE = "en-US-AndrewNeural"

# Edge TTS has no documented request-size limit like Chirp's ~5,000 bytes, but
# a long section (2,000+ chars) is still split on sentence boundaries so any
# single synthesis call stays small and a transient failure only costs one
# chunk, not the whole section — see plan/phase-2-real-voice.md §2.1.
MAX_CHUNK_CHARS = 1800


def _edge_rate(rate: float) -> str:
    pct = round((rate - 1.0) * 100)
    return f"{'+' if pct >= 0 else ''}{pct}%"


class EdgeTTS:
    """Microsoft Edge TTS — free, no API key, but an unofficial API that could
    break without notice (see plan/phase-2-real-voice.md risk section — this is
    why providers.tts.fallback is wired through registry.resolve_provider() in
    s05_assets.py rather than assumed reliable).

    Chunks long text on sentence boundaries, synthesizes each chunk, joins them
    with ffmpeg concat (stream copy — safe since every chunk shares the same
    voice/codec/sample rate), then runs a single loudnorm pass so loudness is
    consistent regardless of how many chunks a section needed.
    """

    def __init__(self, model: str, options: dict):
        self.id = f"{ID_PREFIX}/{model}"
        self.model = model
        self.options = options

    def estimate_cost(self, req: TTSRequest) -> Money:
        return Money(usd=0.0)

    def health_check(self) -> HealthStatus:
        try:
            require_ffmpeg_tools()
        except FFmpegNotFound as e:
            return HealthStatus(ok=False, detail=str(e))
        try:
            with tempfile.TemporaryDirectory() as tmp:
                probe_path = Path(tmp) / "probe.mp3"
                asyncio.run(self._synthesize_chunk("test", DEFAULT_VOICE, "+0%", probe_path))
                if not probe_path.exists() or probe_path.stat().st_size == 0:
                    return HealthStatus(ok=False, detail="edge-tts returned no audio for a test phrase")
            return HealthStatus(ok=True)
        except Exception as e:  # noqa: BLE001 — health check reports, never raises
            return HealthStatus(ok=False, detail=str(e))

    def synthesize(self, req: TTSRequest) -> TTSResult:
        require_ffmpeg_tools()
        voice = req.voice_id or DEFAULT_VOICE
        rate = _edge_rate(req.rate)

        chunks = split_into_sentence_chunks(req.text, MAX_CHUNK_CHARS)
        if not chunks:
            raise ValueError(f"'{self.id}' synthesize called with empty text")

        out_path = Path(req.out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory() as tmp:
            chunk_paths = []
            for i, chunk in enumerate(chunks):
                chunk_path = Path(tmp) / f"chunk_{i}.mp3"
                asyncio.run(self._synthesize_chunk(chunk, voice, rate, chunk_path))
                chunk_paths.append(str(chunk_path))

            joined_path = Path(tmp) / "joined.mp3"
            concat_audio(chunk_paths, str(joined_path))
            normalize_loudness(str(joined_path), str(out_path))

        return TTSResult(
            audio_path=str(out_path),
            duration_sec=probe_duration_sec(str(out_path)),
            char_count=len(req.text),
        )

    async def _synthesize_chunk(self, text: str, voice: str, rate: str, out_path: Path) -> None:
        communicate = edge_tts.Communicate(text, voice, rate=rate)
        await communicate.save(str(out_path))


def get_adapter(model: str, options: dict) -> EdgeTTS:
    return EdgeTTS(model, options)
