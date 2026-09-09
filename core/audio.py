from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

LOUDNORM_FILTER = "loudnorm=I=-16:TP=-1.5:LRA=11"  # -16 LUFS: YouTube's spoken-content target


class FFmpegNotFound(RuntimeError):
    pass


def require_ffmpeg_tools() -> None:
    """Raise clearly if ffmpeg/ffprobe aren't on PATH. Call this from a TTS
    adapter's health_check() (see plan/phase-2-real-voice.md §2.2) so a missing
    binary fails fast instead of surfacing mid-synthesis at render time."""
    missing = [tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None]
    if missing:
        raise FFmpegNotFound(f"{', '.join(missing)} not found on PATH — install ffmpeg (it bundles ffprobe).")


def probe_duration_sec(path: str) -> float:
    """Real audio duration via ffprobe. Every TTS adapter that writes a real
    file should measure duration this way rather than estimating it — see
    plan/phase-2-real-voice.md §2.2 (local_fake.py is the sole exception since
    it writes a 0-byte placeholder)."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True, text=True, check=True,
    )
    return round(float(result.stdout.strip()), 2)


def concat_audio(chunk_paths: list[str], out_path: str) -> None:
    """Join same-codec/same-sample-rate audio chunks via ffmpeg's concat demuxer
    (stream copy, no re-encode) — safe here because all chunks come from the
    same TTS call, but not a general-purpose audio joiner."""
    if len(chunk_paths) == 1:
        shutil.copyfile(chunk_paths[0], out_path)
        return
    list_path = Path(out_path).with_suffix(".concat.txt")
    list_path.write_text("\n".join(f"file '{Path(p).resolve()}'" for p in chunk_paths))
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy", out_path],
            check=True, capture_output=True,
        )
    finally:
        list_path.unlink(missing_ok=True)


def normalize_loudness(in_path: str, out_path: str) -> None:
    """Single-pass loudnorm to -16 LUFS. Run at the TTS adapter layer, after
    chunk-joining — not in s06_render — so every provider's output ends up at
    the same loudness regardless of how many chunks it was synthesized in
    (see plan/phase-2-real-voice.md §2.3)."""
    subprocess.run(
        ["ffmpeg", "-y", "-i", in_path, "-af", LOUDNORM_FILTER, out_path],
        check=True, capture_output=True,
    )
