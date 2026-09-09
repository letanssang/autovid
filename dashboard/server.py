from __future__ import annotations

import html
from pathlib import Path

import yaml
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from core.env import load_env
from core.state import GATED_STAGES, STAGES, ProjectState

load_env()

# Minimal read-only status page — the full HTMX/Alpine dashboard (gate
# approve/reject UI, artifact previews, budget graphs) is M2 scope, see
# AutoVid master plan §8, §11.
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
        rows.append(
            f"<tr><td><a href='/projects/{p.name}'>{p.name}</a> "
            f"[<a href='/projects/{p.name}/config'>config</a>]</td>{cells}</tr>"
        )

    header = "".join(f"<th>{s}</th>" for s in STAGES)
    body = "".join(rows) or f'<tr><td colspan="{len(STAGES) + 1}">No projects yet</td></tr>'
    return (
        "<html><head><title>AutoVid</title></head><body>"
        "<h1>AutoVid projects</h1>"
        f'<table border="1" cellpadding="6"><tr><th>project</th>{header}</tr>{body}</table>'
        "</body></html>"
    )


@app.get("/projects/{name}")
def project_detail(name: str) -> dict:
    root = PROJECTS_DIR / name
    if not (root / "project.yaml").exists():
        return {"error": f"no project '{name}'"}
    state = ProjectState(root=root)
    return {
        "project": name,
        "config": state.load_config(),
        "stages": {
            s: {
                "ran": state.has_run(s),
                "approved": state.is_approved(s) if s in GATED_STAGES else None,
            }
            for s in STAGES
        },
    }


@app.post("/projects/{name}/approve/{stage}")
def approve_stage(name: str, stage: str) -> dict:
    root = PROJECTS_DIR / name
    if not (root / "project.yaml").exists():
        return {"error": f"no project '{name}'"}
    if stage not in GATED_STAGES:
        return {"error": f"'{stage}' has no approval gate"}
    ProjectState(root=root).approve(stage)
    return {"project": name, "stage": stage, "approved": True}


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
