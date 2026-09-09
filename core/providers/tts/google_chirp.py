from __future__ import annotations

import base64
import tempfile
import time
from pathlib import Path

import httpx

from core.audio import (
    FFmpegNotFound,
    concat_audio,
    normalize_loudness,
    probe_duration_sec,
    require_ffmpeg_tools,
)
from core.env import require_key
from core.providers import pricing
from core.providers.contracts import HealthStatus, Money, TTSRequest, TTSResult
from core.providers.tts._shared import split_into_sentence_chunks

ID_PREFIX = "google"
API_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"
DEFAULT_VOICE = "en-US-Chirp3-HD-Iapetus"
MAX_RETRIES = 3
RETRY_DELAYS_SEC = [1, 4, 10]

# Chirp 3 HD's synchronous synthesize endpoint caps input around 5,000 bytes
# (same limit edge.py's docstring references) — chunk well under that so a
# multi-byte-heavy locale doesn't overrun it.
MAX_CHUNK_CHARS = 4500


class GoogleChirpTTS:
    """Chirp 3 HD via Google Cloud Text-to-Speech — official API, free up to
    1M chars/month then $30/1M (see core/providers/pricing.yaml). Meant as the
    reliable fallback behind providers.tts.default: edge/tts, which is a free
    but unofficial API that can break without notice.

    Required in project.yaml -> providers.tts.options:
      api_key_env: name of the .env variable holding a Google Cloud API key
                   with the Text-to-Speech API enabled.

    Chunks on sentence boundaries, synthesizes each chunk, joins with ffmpeg
    concat, then loudnorms once — same pipeline as edge.py so both providers
    converge to the same loudness.
    """

    def __init__(self, model: str, options: dict):
        self.id = f"{ID_PREFIX}/{model}"
        self.model = model
        self.options = options
        self.api_key_env = options.get("api_key_env", "")
        if not self.api_key_env:
            raise ValueError(
                "providers.tts.options.api_key_env is required for the 'google' vendor "
                "(name of the .env variable holding your Google Cloud API key with the "
                "Text-to-Speech API enabled) — set it via `autovid config set` or the "
                "dashboard's project config page."
            )

    def _api_key(self) -> str:
        return require_key(self.api_key_env, self.id)

    def _voice_for(self, req: TTSRequest) -> str:
        # providers.tts.options.voice is shared across the whole fallback chain
        # (see Registry.options() / s05_assets.py) — a voice name meant for a
        # different vendor (e.g. edge's "en-US-AndrewNeural") would otherwise be
        # sent straight to Google's API and 400. Fall back to our own default
        # when the given id isn't a Chirp voice name.
        if req.voice_id and "Chirp3-HD" in req.voice_id:
            return req.voice_id
        return DEFAULT_VOICE

    def estimate_cost(self, req: TTSRequest) -> Money:
        return Money(usd=pricing.tts_cost_usd(self.id, len(req.text)) or 0.0)

    def health_check(self) -> HealthStatus:
        try:
            require_ffmpeg_tools()
        except FFmpegNotFound as e:
            return HealthStatus(ok=False, detail=str(e))
        try:
            resp = httpx.post(
                API_URL,
                params={"key": self._api_key()},
                json={
                    "input": {"text": "test"},
                    "voice": {"languageCode": "en-US", "name": DEFAULT_VOICE},
                    "audioConfig": {"audioEncoding": "MP3"},
                },
                timeout=10,
            )
            if resp.status_code >= 400:
                return HealthStatus(ok=False, detail=f"POST {API_URL} -> {resp.status_code} {resp.text[:300]}")
            return HealthStatus(ok=True)
        except Exception as e:  # noqa: BLE001 — health check reports, never raises
            return HealthStatus(ok=False, detail=str(e))

    def synthesize(self, req: TTSRequest) -> TTSResult:
        require_ffmpeg_tools()
        voice = self._voice_for(req)
        language_code = "-".join(voice.split("-")[:2])
        rate = max(0.25, min(4.0, req.rate))

        chunks = split_into_sentence_chunks(req.text, MAX_CHUNK_CHARS)
        if not chunks:
            raise ValueError(f"'{self.id}' synthesize called with empty text")

        out_path = Path(req.out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory() as tmp:
            chunk_paths = []
            for i, chunk in enumerate(chunks):
                chunk_path = Path(tmp) / f"chunk_{i}.mp3"
                self._synthesize_chunk(chunk, voice, language_code, rate, chunk_path)
                chunk_paths.append(str(chunk_path))

            joined_path = Path(tmp) / "joined.mp3"
            concat_audio(chunk_paths, str(joined_path))
            normalize_loudness(str(joined_path), str(out_path))

        return TTSResult(
            audio_path=str(out_path),
            duration_sec=probe_duration_sec(str(out_path)),
            char_count=len(req.text),
        )

    def _synthesize_chunk(self, text: str, voice: str, language_code: str, rate: float, out_path: Path) -> None:
        last_error = ""
        for attempt in range(MAX_RETRIES):
            try:
                resp = httpx.post(
                    API_URL,
                    params={"key": self._api_key()},
                    json={
                        "input": {"text": text},
                        "voice": {"languageCode": language_code, "name": voice},
                        "audioConfig": {"audioEncoding": "MP3", "speakingRate": rate},
                    },
                    timeout=30,
                )
            except httpx.RequestError as e:
                last_error = str(e)
            else:
                if resp.status_code == 429 or resp.status_code >= 500:
                    last_error = f"{resp.status_code}: {resp.text[:500]}"
                elif resp.status_code >= 400:
                    raise RuntimeError(f"'{self.id}' synthesize failed: {resp.status_code} {resp.text[:1000]}")
                else:
                    out_path.write_bytes(base64.b64decode(resp.json()["audioContent"]))
                    return
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAYS_SEC[attempt])
        raise RuntimeError(f"'{self.id}' synthesize failed after {MAX_RETRIES} attempts: {last_error}")


def get_adapter(model: str, options: dict) -> GoogleChirpTTS:
    return GoogleChirpTTS(model, options)
