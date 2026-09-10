from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

STAGE = "06_render"

DEFAULT_FPS = 30
TIME_RE = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")
PROGRESS_THROTTLE_SEC = 2.0


def run(project_root: Path, config: dict, preview_sec: float | None = None, progress_cb: Callable[[str], None] | None = None) -> None:
    assets = json.loads((project_root / "05_assets" / "assets_manifest.json").read_text())
    visual_plan = json.loads((project_root / "04_visual_plan" / "visual_plan.json").read_text())
    script = json.loads((project_root / "03_script" / "script.json").read_text())

    audio_by_section = {a["section_id"]: a for a in assets["audio"]}
    visuals_by_beat = {v["beat_id"]: v for v in assets["visuals"]}

    timeline = []
    srt_entries = []
    cursor_sec = 0.0
    for section in script["sections"]:
        audio = audio_by_section.get(section["id"])
        section_duration = audio["duration_sec"] if audio else 0.0
        beats = [b for b in visual_plan["beats"] if b["section_id"] == section["id"]]
        beat_duration = section_duration / max(len(beats), 1)

        for beat in beats:
            beat_id = f"{beat['section_id']}-{beat['beat_index']}"
            visual = visuals_by_beat.get(beat_id, {})
            start, end = cursor_sec, cursor_sec + beat_duration
            timeline.append({
                "beat_id": beat_id,
                "section_id": section["id"],
                "asset_path": visual.get("asset_path"),
                "visual_type": visual.get("type", "b_roll"),
                "start_sec": round(start, 2),
                "end_sec": round(end, 2),
                "audio_path": audio["audio_path"] if audio else None,
                "text": beat["text"],
            })
            srt_entries.append((start, end, beat["text"]))
            cursor_sec = end

    out_dir = project_root / STAGE
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "render_manifest.json").write_text(json.dumps({
        "timeline": timeline, "total_duration_sec": round(cursor_sec, 2),
    }, indent=2))
    (out_dir / "subtitles.srt").write_text(_render_srt(srt_entries))

    # Every beat must resolve to a real visual asset (plan/phase-3-first-video.md
    # §3.2) — s05_assets.py no longer emits asset_path: None for b_roll beats, so
    # a mismatch here means an upstream bug, not an expected degraded state.
    beats_with_asset = [b for b in timeline if b["asset_path"]]
    if len(beats_with_asset) != len(timeline):
        missing = [b["beat_id"] for b in timeline if not b["asset_path"]]
        (out_dir / "render_status.json").write_text(json.dumps({
            "rendered": False,
            "reason": (
                f"{len(missing)} beat(s) have no visual asset (run 05_assets first): {missing}"
            ),
        }, indent=2))
        return

    if shutil.which("ffmpeg") is None:
        (out_dir / "render_status.json").write_text(json.dumps({
            "rendered": False,
            "reason": "ffmpeg not found on PATH — install ffmpeg to produce output.mp4",
        }, indent=2))
        return

    fps = (config.get("video") or {}).get("fps", DEFAULT_FPS)
    _render_with_ffmpeg(out_dir, timeline, audio_by_section, cursor_sec, fps, preview_sec, progress_cb)


def _render_srt(entries: list[tuple[float, float, str]]) -> str:
    lines = []
    for i, (start, end, text) in enumerate(entries, start=1):
        lines.append(str(i))
        lines.append(f"{_srt_ts(start)} --> {_srt_ts(end)}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines)


def _srt_ts(seconds: float) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _render_with_ffmpeg(
    out_dir: Path,
    timeline: list[dict],
    audio_by_section: dict,
    total_duration_sec: float,
    fps: int,
    preview_sec: float | None,
    progress_cb: Callable[[str], None] | None,
) -> None:
    audio_paths = [a["audio_path"] for a in audio_by_section.values() if a.get("audio_path")]

    if not audio_paths or not timeline:
        (out_dir / "render_status.json").write_text(json.dumps({
            "rendered": False,
            "reason": "missing audio or visual assets — run 05_assets with real (non-placeholder) providers first",
        }, indent=2))
        return

    log_path = out_dir / "ffmpeg.log"
    log_path.write_text("")  # fresh log per render, kept only on failure for debugging

    concat_audio_list = out_dir / "_audio_concat.txt"
    concat_audio_list.write_text("\n".join(f"file '{Path(p).resolve()}'" for p in audio_paths))
    narration_path = out_dir / "_narration.mp3"
    concat_result = subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_audio_list), "-c", "copy", str(narration_path)],
        check=False, capture_output=True, text=True,
    )
    with log_path.open("a") as f:
        f.write(concat_result.stderr)

    # -filter_complex_script (read the graph from a file) isn't supported by
    # every ffmpeg build (dropped in some recent CLI rewrites — verified absent
    # on ffmpeg 9.0.1 here), so the graph is passed inline via -filter_complex.
    # subprocess.run's argv (no shell involved) isn't subject to a shell's
    # command-length limit, and even a ~200-beat filter graph stays well under
    # the OS argv-size ceiling — the file is written purely as a debug artifact.
    filter_complex = _build_filter_complex(timeline)
    filter_script_path = out_dir / "_filter_complex.txt"
    filter_script_path.write_text(filter_complex)

    output_path = out_dir / "output.mp4"
    cmd = ["ffmpeg", "-y"]
    for beat in timeline:
        duration = max(beat["end_sec"] - beat["start_sec"], 0.1)
        cmd += ["-loop", "1", "-t", f"{duration:.3f}", "-i", str(Path(beat["asset_path"]).resolve())]
    narration_input_idx = len(timeline)
    cmd += ["-i", str(narration_path)]
    cmd += ["-filter_complex", filter_complex]
    cmd += ["-map", "[outv]", "-map", f"{narration_input_idx}:a"]
    cmd += ["-r", str(fps), "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-pix_fmt", "yuv420p"]
    cmd += ["-c:a", "aac", "-shortest"]
    if preview_sec is not None:
        cmd += ["-t", str(preview_sec)]
    cmd += [str(output_path)]

    display_duration = min(total_duration_sec, preview_sec) if preview_sec is not None else total_duration_sec
    returncode, stderr_tail = _run_ffmpeg_streaming(cmd, log_path, progress_cb, display_duration)

    rendered = returncode == 0 and output_path.exists()
    (out_dir / "render_status.json").write_text(json.dumps({
        "rendered": rendered,
        "ffmpeg_log": str(log_path),
        **({} if rendered else {"ffmpeg_stderr_tail": stderr_tail}),
    }, indent=2))

    if rendered:
        for intermediate in (concat_audio_list, narration_path, filter_script_path):
            intermediate.unlink(missing_ok=True)


def _build_filter_complex(timeline: list[dict]) -> str:
    filters = []
    for i in range(len(timeline)):
        filters.append(
            f"[{i}:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
            f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1[v{i}]"
        )
    concat_inputs = "".join(f"[v{i}]" for i in range(len(timeline)))
    filters.append(f"{concat_inputs}concat=n={len(timeline)}:v=1:a=0[outv]")
    return ";\n".join(filters)


def _run_ffmpeg_streaming(
    cmd: list[str], log_path: Path, progress_cb: Callable[[str], None] | None, total_duration_sec: float
) -> tuple[int, str]:
    """Stream ffmpeg's stderr into log_path as it's produced (encoding a full
    video takes minutes — capture_output=True would run silently the whole
    time) while emitting throttled progress lines via progress_cb, parsed from
    ffmpeg's own `time=` stats. Returns (exit code, last ~2000 chars of stderr)."""
    tail = ""
    last_emit = 0.0
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    with log_path.open("a") as log_f:
        for line in proc.stderr:
            log_f.write(line)
            tail = (tail + line)[-2000:]
            match = TIME_RE.search(line)
            if match and progress_cb is not None:
                now = time.monotonic()
                if now - last_emit >= PROGRESS_THROTTLE_SEC:
                    last_emit = now
                    h, m, s = match.groups()
                    elapsed = int(h) * 3600 + int(m) * 60 + float(s)
                    progress_cb(f"rendering... {elapsed:.0f}s / {total_duration_sec:.0f}s")
    proc.wait()
    return proc.returncode, tail
