from __future__ import annotations

from pathlib import Path

from core.providers.contracts import HealthStatus, Money, TTSRequest, TTSResult

ID = "local/fake"
WORDS_PER_MINUTE = 150


class LocalFakeTTS:
    id = ID

    def estimate_cost(self, req: TTSRequest) -> Money:
        return Money(usd=0.0)

    def health_check(self) -> HealthStatus:
        return HealthStatus(ok=True, detail="silent placeholder audio, no network")

    def synthesize(self, req: TTSRequest) -> TTSResult:
        # Writes a 0-byte file, so duration_sec can't be probed with ffprobe like
        # every other TTS adapter does (core/audio.py::probe_duration_sec) — this
        # is a words-per-minute ESTIMATE, not a real measurement. Don't trust it
        # for timeline/subtitle sync; switch to a real provider (e.g. edge/tts)
        # for that. See plan/phase-2-real-voice.md §2.2.
        word_count = max(len(req.text.split()), 1)
        duration_sec = round(word_count / WORDS_PER_MINUTE * 60, 2)
        out_path = Path(req.out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"")
        return TTSResult(audio_path=str(out_path), duration_sec=duration_sec, char_count=len(req.text))


def get_adapter(model: str, options: dict) -> LocalFakeTTS:
    return LocalFakeTTS()
