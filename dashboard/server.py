from __future__ import annotations

import html
import json
import shutil
from pathlib import Path
from urllib.parse import quote

import yaml
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from core import manual_assets, packaging
from core.env import load_env
from core.providers.registry import BudgetExceeded
from core.state import GATED_STAGES, STAGES, ProjectState

load_env()

# Single-user localhost tool — plain HTML forms, no auth, no WebSocket, no
# build step (plan/phase-6-publish-package.md §6.3 "Rủi ro"). Approve/reject
# happen here; actually advancing the pipeline is still `autovid run` from a
# terminal.
app = FastAPI(title="AutoVid Dashboard")

ROOT = Path(__file__).resolve().parent.parent
PROJECTS_DIR = ROOT / "projects"

CAPABILITIES = ["text", "research", "tts", "image", "video_clip", "slides", "publish"]


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    projects = []
    if PROJECTS_DIR.exists():
        projects = sorted(p for p in PROJECTS_DIR.iterdir() if (p / "project.yaml").exists())

    rows = []
    for p in projects:
        state = ProjectState(root=p)
        cells = "".join(
            f"<td>{'x' if state.has_run(s) else '-'}"
            f"{' (approved)' if s in GATED_STAGES and state.is_approved(s) else ''}</td>"
            for s in STAGES
        )
        pending_count = len(manual_assets.list_pending(p))
        manual_link = f" [<a href='/projects/{p.name}/manual-assets'>manual assets ({pending_count})</a>]" if pending_count else ""
        rows.append(
            f"<tr><td><a href='/projects/{p.name}'>{p.name}</a> "
            f"[<a href='/projects/{p.name}/config'>config</a>]{manual_link}</td>{cells}</tr>"
        )

    header = "".join(f"<th>{s}</th>" for s in STAGES)
    body = "".join(rows) or f'<tr><td colspan="{len(STAGES) + 1}">No projects yet</td></tr>'
    return (
        "<html><head><title>AutoVid</title></head><body>"
        "<h1>AutoVid projects</h1>"
        f'<table border="1" cellpadding="6"><tr><th>project</th>{header}</tr>{body}</table>'
        "</body></html>"
    )


STAGE_MD = {
    "01_research": "research.md",
    "02_outline": "outline.md",
    "03_script": "script.md",
    "04_visual_plan": "visual_plan.md",
}


def _read_text(path: Path) -> str:
    return path.read_text() if path.exists() else ""


def _rel_file_url(name: str, root: Path, abs_path: str | None) -> str | None:
    """Maps an absolute asset path from a stage manifest to this dashboard's
    file-serving route, project-relative — never trust a manifest path
    straight into an <img>/<audio>/<video> src."""
    if not abs_path:
        return None
    try:
        rel = Path(abs_path).resolve().relative_to(root.resolve())
    except ValueError:
        return None
    return f"/projects/{name}/file/{rel.as_posix()}"


def _gate_controls(name: str, state: ProjectState, stage: str) -> str:
    if stage not in GATED_STAGES:
        return ""
    if state.is_approved(stage):
        return "<p style='color:green'>Đã duyệt ✓</p>"
    rejected_html = ""
    if state.is_rejected(stage):
        note = html.escape(state.rejection_note(stage))
        rejected_html = (
            f"<p style='color:#b30000'>Đã từ chối — lý do: {note}<br>"
            f"Chạy <code>autovid run {html.escape(name)}</code> để tạo lại với lý do này.</p>"
        )
    return (
        rejected_html
        + f"<form method='post' action='/projects/{name}/approve/{stage}' style='display:inline-block;margin-right:8px'>"
        + "<button type='submit'>Duyệt</button></form>"
        + f"<form method='post' action='/projects/{name}/reject/{stage}' style='display:inline-block'>"
        + "<input name='note' placeholder='Lý do từ chối' required size='40'> "
        + "<button type='submit'>Từ chối</button></form>"
    )


def _stage_preview(name: str, root: Path, stage: str) -> str:
    stage_dir = root / stage

    if stage in STAGE_MD:
        text = _read_text(stage_dir / STAGE_MD[stage])
        if not text:
            return "<p><em>(chưa có artifact)</em></p>"
        return (
            "<pre style='white-space:pre-wrap;max-height:400px;overflow:auto;"
            f"border:1px solid #ccc;padding:8px'>{html.escape(text)}</pre>"
        )

    if stage == "05_assets":
        return _assets_preview(name, root, stage_dir)

    if stage == "06_render":
        return _render_preview(name, stage_dir)

    if stage == "07_publish":
        return _publish_preview(name, root, stage_dir)

    return ""


def _assets_preview(name: str, root: Path, stage_dir: Path) -> str:
    manifest_path = stage_dir / "assets_manifest.json"
    if not manifest_path.exists():
        return "<p><em>(chưa có artifact)</em></p>"
    manifest = json.loads(manifest_path.read_text())

    parts = []
    pending = manual_assets.list_pending(root)
    if pending:
        parts.append(
            f"<p style='color:#b30000'><a href='/projects/{name}/manual-assets'>"
            f"{len(pending)} beat cần ảnh thủ công</a></p>"
        )

    audio = manifest.get("audio", [])
    visuals = manifest.get("visuals", [])
    parts.append(f"<p>{len(audio)} audio · {len(visuals)} visual</p>")

    audio_rows = []
    for a in audio:
        url = _rel_file_url(name, root, a.get("audio_path"))
        if url:
            audio_rows.append(
                f"<div>{html.escape(a['section_id'])} "
                f"<audio controls src='{url}' style='vertical-align:middle;height:28px'></audio></div>"
            )
    if audio_rows:
        parts.append("<details><summary>Audio</summary>" + "".join(audio_rows) + "</details>")

    visual_cells = []
    for v in visuals:
        url = _rel_file_url(name, root, v.get("asset_path"))
        if url:
            visual_cells.append(
                "<figure style='width:150px;margin:0;font-size:11px'>"
                f"<img src='{url}' style='width:150px' loading='lazy'>"
                f"<figcaption>{html.escape(v['beat_id'])} ({html.escape(v['type'])})</figcaption></figure>"
            )
    if visual_cells:
        parts.append(
            "<details open><summary>Visuals</summary><div style='display:flex;flex-wrap:wrap;gap:8px'>"
            + "".join(visual_cells) + "</div></details>"
        )
    return "".join(parts)


def _render_preview(name: str, stage_dir: Path) -> str:
    parts = []
    video_path = stage_dir / "output.mp4"
    if video_path.exists() and video_path.stat().st_size > 0:
        parts.append(f"<video controls style='max-width:640px' src='/projects/{name}/file/06_render/output.mp4'></video>")
    else:
        status_path = stage_dir / "render_status.json"
        reason = "chưa render"
        if status_path.exists():
            reason = json.loads(status_path.read_text()).get("reason", reason)
        parts.append(f"<p><em>Chưa có output.mp4 — {html.escape(reason)}</em></p>")

    srt_text = _read_text(stage_dir / "subtitles.srt")
    if srt_text:
        preview = "\n".join(srt_text.splitlines()[:20])
        parts.append(
            "<details><summary>subtitles.srt (20 dòng đầu)</summary>"
            f"<pre style='white-space:pre-wrap'>{html.escape(preview)}</pre></details>"
        )
    return "".join(parts)


def _publish_preview(name: str, root: Path, stage_dir: Path) -> str:
    parts = []
    meta_path = stage_dir / "metadata.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        parts.append(
            f"<p><strong>Title:</strong> {html.escape(meta.get('title', ''))}</p>"
            "<details open><summary>Description</summary>"
            "<pre style='white-space:pre-wrap;max-height:300px;overflow:auto;"
            f"border:1px solid #ccc;padding:8px'>{html.escape(meta.get('description', ''))}</pre></details>"
            f"<p><strong>Tags:</strong> {html.escape(', '.join(meta.get('tags', [])))}</p>"
        )
    else:
        parts.append("<p><em>(chưa có metadata)</em></p>")

    chosen_path = stage_dir / ".thumbnail_choice"
    chosen = chosen_path.read_text().strip() if chosen_path.exists() else "a"
    variant_cells = []
    for letter in ("a", "b", "c"):
        vpath = stage_dir / f"thumbnail_{letter}.png"
        if not vpath.exists() or vpath.stat().st_size == 0:
            continue
        url = f"/projects/{name}/file/07_publish/thumbnail_{letter}.png"
        if letter == chosen:
            action_html = "<div>✓ đang dùng</div>"
        else:
            action_html = (
                f"<form method='post' action='/projects/{name}/publish/thumbnail/{letter}'>"
                "<button type='submit'>Dùng bản này</button></form>"
            )
        variant_cells.append(
            f"<div style='width:280px'><img src='{url}' style='width:280px'><div>{letter.upper()}</div>{action_html}</div>"
        )
    if variant_cells:
        parts.append("<div style='display:flex;gap:12px;flex-wrap:wrap'>" + "".join(variant_cells) + "</div>")
    else:
        parts.append("<p><em>(chưa có thumbnail)</em></p>")

    parts.append(
        f"<form method='post' action='/projects/{name}/package'>"
        "<button type='submit'>Đóng gói để upload (autovid package)</button></form>"
    )
    upload_dir = stage_dir / "upload"
    if upload_dir.exists():
        files = sorted(p.name for p in upload_dir.iterdir() if p.is_file())
        if files:
            links = "".join(
                f"<li><a href='/projects/{name}/file/07_publish/upload/{f}'>{html.escape(f)}</a></li>" for f in files
            )
            parts.append(f"<p>Đã đóng gói tại <code>07_publish/upload/</code>:</p><ul>{links}</ul>")
    return "".join(parts)


@app.get("/projects/{name}", response_class=HTMLResponse)
def project_detail(name: str, error: str = "") -> HTMLResponse:
    root = _project_root(name)
    if root is None:
        return HTMLResponse(f"<p>No project '{html.escape(name)}'</p>", status_code=404)
    state = ProjectState(root=root)

    sections = []
    for stage in STAGES:
        ran = state.has_run(stage)
        status_label = "đã chạy" if ran else "chưa chạy"
        gate_html = _gate_controls(name, state, stage) if ran else ""
        preview_html = _stage_preview(name, root, stage) if ran else "<p><em>(chưa chạy)</em></p>"
        sections.append(
            "<section style='margin-bottom:24px;padding:12px;border:1px solid #ddd'>"
            f"<h2>{stage} <small style='font-weight:normal'>({status_label})</small></h2>"
            f"{gate_html}{preview_html}</section>"
        )

    error_html = f"<p style='color:red'>{html.escape(error)}</p>" if error else ""
    return HTMLResponse(
        f"<html><head><title>AutoVid — {html.escape(name)}</title></head><body>"
        f"<h1>{html.escape(name)}</h1>"
        f"<p><a href='/'>&larr; projects</a> · <a href='/projects/{name}/config'>config</a></p>"
        + error_html
        + "".join(sections)
        + "</body></html>"
    )


@app.post("/projects/{name}/approve/{stage}")
def approve_stage(name: str, stage: str) -> RedirectResponse:
    root = PROJECTS_DIR / name
    if not (root / "project.yaml").exists() or stage not in GATED_STAGES:
        return RedirectResponse(f"/projects/{name}", status_code=303)

    state = ProjectState(root=root)
    config = state.load_config()
    if stage == "01_research" and (config.get("video") or {}).get("high_stakes", False):
        research_md = root / "01_research" / "research.md"
        if research_md.exists() and "[UNSOURCED]" in research_md.read_text():
            msg = "Refusing to approve: high_stakes project still has [UNSOURCED] claims in research.md"
            return RedirectResponse(f"/projects/{name}?error={quote(msg)}", status_code=303)

    state.approve(stage)
    return RedirectResponse(f"/projects/{name}", status_code=303)


@app.post("/projects/{name}/reject/{stage}")
def reject_stage(name: str, stage: str, note: str = Form(...)) -> RedirectResponse:
    root = PROJECTS_DIR / name
    if (root / "project.yaml").exists() and stage in GATED_STAGES:
        ProjectState(root=root).reject(stage, note)
    return RedirectResponse(f"/projects/{name}", status_code=303)


@app.post("/projects/{name}/publish/thumbnail/{variant}")
def choose_thumbnail(name: str, variant: str) -> RedirectResponse:
    root = _project_root(name)
    if root is not None and variant in ("a", "b", "c"):
        src = root / "07_publish" / f"thumbnail_{variant}.png"
        if src.exists() and src.stat().st_size > 0:
            shutil.copy(src, root / "07_publish" / "thumbnail.png")
            (root / "07_publish" / ".thumbnail_choice").write_text(variant)
    return RedirectResponse(f"/projects/{name}", status_code=303)


@app.post("/projects/{name}/package")
def package_project(name: str) -> RedirectResponse:
    root = _project_root(name)
    if root is None:
        return RedirectResponse(f"/projects/{name}", status_code=303)
    try:
        packaging.package(root)
    except FileNotFoundError as e:
        return RedirectResponse(f"/projects/{name}?error={quote(str(e))}", status_code=303)
    return RedirectResponse(f"/projects/{name}", status_code=303)


@app.get("/projects/{name}/file/{path:path}")
def project_file(name: str, path: str) -> FileResponse:
    root = _project_root(name)
    if root is None:
        raise HTTPException(404, f"no project '{name}'")
    target = (root / path).resolve()
    if not target.is_relative_to(root.resolve()) or not target.is_file():
        raise HTTPException(404, "file not found")
    return FileResponse(target)


def _config_path(name: str) -> Path | None:
    path = PROJECTS_DIR / name / "project.yaml"
    return path if path.exists() else None


@app.get("/projects/{name}/config", response_class=HTMLResponse)
def project_config(name: str) -> HTMLResponse:
    path = _config_path(name)
    if path is None:
        return HTMLResponse(f"<p>No project '{html.escape(name)}'</p>", status_code=404)

    config = yaml.safe_load(path.read_text()) or {}
    providers = config.get("providers", {}) or {}

    sections = []
    for cap in CAPABILITIES:
        cfg = providers.get(cap) or {}
        default = html.escape(str(cfg.get("default") or ""))
        options = cfg.get("options") or {}
        base_url = html.escape(str(options.get("base_url") or ""))
        api_key_env = html.escape(str(options.get("api_key_env") or ""))
        sections.append(
            f"<fieldset><legend>{cap}</legend>"
            f"<form method='post' action='/projects/{name}/config/{cap}'>"
            f"<label>default provider (vendor/model) "
            f"<input name='default' value='{default}' placeholder='e.g. custom/opus' size='40'></label><br>"
            f"<label>options.base_url "
            f"<input name='base_url' value='{base_url}' placeholder='http://localhost:20128/v1' size='40'></label><br>"
            f"<label>options.api_key_env "
            f"<input name='api_key_env' value='{api_key_env}' placeholder='NINEROUTER_API_KEY' size='40'></label><br>"
            f"<button type='submit'>Save</button>"
            f"</form></fieldset>"
        )

    return HTMLResponse(
        "<html><head><title>AutoVid config</title></head><body>"
        f"<h1>Provider config — {html.escape(name)}</h1>"
        f"<p><a href='/'>&larr; projects</a></p>"
        f"<p>Vendor <code>custom</code> talks to any OpenAI-compatible endpoint "
        f"(e.g. a local router) — set base_url + api_key_env, and put the real key "
        f"in .env under that variable name.</p>"
        + "".join(sections)
        + "</body></html>"
    )


@app.post("/projects/{name}/config/{capability}")
def project_config_set(
    name: str,
    capability: str,
    default: str = Form(""),
    base_url: str = Form(""),
    api_key_env: str = Form(""),
) -> RedirectResponse:
    path = _config_path(name)
    if path is None or capability not in CAPABILITIES:
        return RedirectResponse(f"/projects/{name}/config", status_code=303)

    config = yaml.safe_load(path.read_text()) or {}
    cap_cfg = config.setdefault("providers", {}).setdefault(capability, {})

    if default.strip():
        cap_cfg["default"] = default.strip()

    options = cap_cfg.setdefault("options", {})
    if base_url.strip():
        options["base_url"] = base_url.strip()
    if api_key_env.strip():
        options["api_key_env"] = api_key_env.strip()

    path.write_text(yaml.dump(config, sort_keys=False))
    return RedirectResponse(f"/projects/{name}/config", status_code=303)


def _project_root(name: str) -> Path | None:
    root = PROJECTS_DIR / name
    return root if (root / "project.yaml").exists() else None


@app.get("/projects/{name}/manual-assets", response_class=HTMLResponse)
def manual_assets_page(name: str, error: str = "") -> HTMLResponse:
    root = _project_root(name)
    if root is None:
        return HTMLResponse(f"<p>No project '{html.escape(name)}'</p>", status_code=404)

    pending = manual_assets.list_pending(root)
    sections = []
    for item in pending:
        beat_id = item["beat_id"]
        prompt_text = html.escape(manual_assets.read_prompt(root, beat_id))
        sections.append(
            f"<fieldset><legend>{html.escape(beat_id)}</legend>"
            f"<p><em>{html.escape(item.get('text', ''))}</em></p>"
            f"<form method='post' action='/projects/{name}/manual-assets/{beat_id}/prompt'>"
            f"<textarea name='text' rows='4' cols='80'>{prompt_text}</textarea><br>"
            f"<button type='submit'>Save prompt</button>"
            f"</form>"
            f"<form method='post' action='/projects/{name}/manual-assets/{beat_id}/improve'>"
            f"<label>AI-improve instruction "
            f"<input name='instruction' size='60' placeholder='e.g. make it more vivid, add warm colors'></label> "
            f"<button type='submit'>Improve with AI</button>"
            f"</form>"
            f"<form method='post' action='/projects/{name}/manual-assets/{beat_id}/upload' enctype='multipart/form-data'>"
            f"<label>Upload finished image <input type='file' name='file' accept='image/png'></label> "
            f"<button type='submit'>Upload</button>"
            f"</form>"
            f"<p>Expected path: <code>{html.escape(item.get('expected_path', ''))}</code></p>"
            f"</fieldset>"
        )

    error_html = f"<p style='color:red'>{html.escape(error)}</p>" if error else ""
    body = "".join(sections) or "<p>No pending manual assets.</p>"
    return HTMLResponse(
        "<html><head><title>AutoVid manual assets</title></head><body>"
        f"<h1>Manual assets — {html.escape(name)}</h1>"
        f"<p><a href='/'>&larr; projects</a></p>"
        + error_html
        + body
        + "</body></html>"
    )


@app.post("/projects/{name}/manual-assets/{beat_id}/prompt")
def manual_assets_set_prompt(name: str, beat_id: str, text: str = Form(...)) -> RedirectResponse:
    root = _project_root(name)
    if root is not None:
        manual_assets.write_prompt(root, beat_id, text)
    return RedirectResponse(f"/projects/{name}/manual-assets", status_code=303)


@app.post("/projects/{name}/manual-assets/{beat_id}/improve")
def manual_assets_improve(name: str, beat_id: str, instruction: str = Form(...)) -> RedirectResponse:
    root = _project_root(name)
    if root is None:
        return RedirectResponse(f"/projects/{name}/manual-assets", status_code=303)
    try:
        manual_assets.improve_prompt(root, beat_id, instruction)
    except (BudgetExceeded, ValueError) as e:
        return RedirectResponse(f"/projects/{name}/manual-assets?error={quote(str(e))}", status_code=303)
    return RedirectResponse(f"/projects/{name}/manual-assets", status_code=303)


@app.post("/projects/{name}/manual-assets/{beat_id}/upload")
async def manual_assets_upload(name: str, beat_id: str, file: UploadFile = File(...)) -> RedirectResponse:  # noqa: B008 — FastAPI's own idiom for file uploads
    root = _project_root(name)
    if root is None:
        return RedirectResponse(f"/projects/{name}/manual-assets", status_code=303)
    try:
        data = await file.read()
        manual_assets.import_asset(root, beat_id, data)
    except ValueError as e:
        return RedirectResponse(f"/projects/{name}/manual-assets?error={quote(str(e))}", status_code=303)
    return RedirectResponse(f"/projects/{name}/manual-assets", status_code=303)
