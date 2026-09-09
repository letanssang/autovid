from __future__ import annotations

import datetime
import json
import re
from pathlib import Path

import typer
import yaml

from core import manual_assets
from core.env import load_env
from core.providers.registry import BudgetExceeded
from core.stages import STAGE_RUNNERS
from core.state import GATED_STAGES, STAGES, ProjectState

load_env()

app = typer.Typer(help="AutoVid — generate a YouTube video from a topic string.")
config_app = typer.Typer(help="Point a capability at a different provider — no code change needed.")
app.add_typer(config_app, name="config")

CAPABILITIES = ["text", "research", "tts", "image", "video_clip", "slides", "publish"]

ROOT = Path(__file__).resolve().parent.parent
PROJECTS_DIR = ROOT / "projects"
PROJECT_TEMPLATE = ROOT / "templates" / "project.yaml.example"


def _slugify(topic: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")
    return slug or "project"


def _project_root(name: str) -> Path:
    root = PROJECTS_DIR / name
    if not root.exists():
        typer.secho(f"No project '{name}' under {PROJECTS_DIR}", fg=typer.colors.RED)
        raise typer.Exit(1)
    return root


def _coerce_option_value(value: str) -> int | float | bool | str:
    """Best-effort type inference for --option key=value, so e.g. rate=1.0 lands as a float, not a string."""
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    return value


@app.command()
def new(topic: str) -> None:
    """Scaffold a new project from templates/project.yaml.example."""
    slug = _slugify(topic)
    project_root = PROJECTS_DIR / slug
    if project_root.exists():
        typer.secho(f"Project '{slug}' already exists at {project_root}", fg=typer.colors.RED)
        raise typer.Exit(1)

    project_root.mkdir(parents=True)
    config = yaml.safe_load(PROJECT_TEMPLATE.read_text())
    config["topic"] = topic
    config["project_name"] = slug
    config["created_at"] = datetime.datetime.now(datetime.UTC).isoformat()
    (project_root / "project.yaml").write_text(yaml.dump(config, sort_keys=False))

    state = ProjectState(root=project_root)
    for stage in STAGES:
        state.stage_dir(stage)

    typer.secho(f"Created project '{slug}' at {project_root}", fg=typer.colors.GREEN)


@app.command()
def status(project: str | None = typer.Argument(None)) -> None:
    """Show pipeline status for one project, or list all projects."""
    if project is None:
        if not PROJECTS_DIR.exists() or not any(PROJECTS_DIR.iterdir()):
            typer.echo('No projects yet — run `autovid new "<topic>"`.')
            return
        for p in sorted(PROJECTS_DIR.iterdir()):
            if (p / "project.yaml").exists():
                typer.echo(p.name)
        return

    root = _project_root(project)
    state = ProjectState(root=root)
    for stage in STAGES:
        ran = state.has_run(stage)
        gated = stage in GATED_STAGES
        marker = "x" if ran else " "
        gate = ""
        if gated:
            gate = " [approved]" if state.is_approved(stage) else " [pending approval]"
        typer.echo(f"[{marker}] {stage}{gate}")


@app.command()
def run(
    project: str,
    from_stage: str | None = typer.Option(None, "--from", help="Stage id to start from, e.g. 03_script"),
    force: bool = typer.Option(False, "--force", help="Run past an unapproved gate"),
    preview: int | None = typer.Option(
        None, "--preview", help="06_render only: render just the first N seconds, for fast iteration"
    ),
) -> None:
    """Run pipeline stages in order, stopping at an unapproved gate."""
    root = _project_root(project)
    state = ProjectState(root=root)
    config = state.load_config()

    if from_stage:
        start_idx = STAGES.index(from_stage)
    else:
        start_idx = next((i for i, s in enumerate(STAGES) if not state.has_run(s)), len(STAGES))
        if start_idx == len(STAGES):
            typer.echo("All stages already ran. Use --from <stage> to re-run one.")
            raise typer.Exit(0)

    for stage in STAGES[start_idx:]:
        prev_idx = STAGES.index(stage) - 1
        if prev_idx >= 0:
            prev_stage = STAGES[prev_idx]
            if prev_stage in GATED_STAGES and not state.is_approved(prev_stage) and not force:
                typer.secho(
                    f"Stopped: '{prev_stage}' is not approved yet (autovid approve {project} {prev_stage})",
                    fg=typer.colors.YELLOW,
                )
                raise typer.Exit(1)

        typer.echo(f"Running {stage}...")
        try:
            if stage == "06_render":
                STAGE_RUNNERS[stage](
                    root, config, preview_sec=preview,
                    progress_cb=lambda line: typer.echo(f"  {line}"),
                )
            else:
                STAGE_RUNNERS[stage](root, config)
        except BudgetExceeded as e:
            typer.secho(f"Stopped: {e}", fg=typer.colors.RED)
            raise typer.Exit(1)
        typer.secho("  done", fg=typer.colors.GREEN)

        if stage == "05_assets":
            status_path = root / "05_assets" / "slide_render_status.json"
            if status_path.exists():
                degraded = json.loads(status_path.read_text()).get("degraded", [])
                if degraded:
                    typer.secho(
                        f"  warning: {len(degraded)} slide(s) rendered as empty PNGs — see {status_path}",
                        fg=typer.colors.YELLOW,
                    )

            pending = manual_assets.list_pending(root)
            if pending:
                typer.secho(
                    f"  {len(pending)} beat(s) need a manually-created image before rendering can continue:",
                    fg=typer.colors.YELLOW,
                )
                for item in pending:
                    typer.echo(f"    - {item['beat_id']}")
                typer.echo(
                    f"  Run `autovid ui` and open http://127.0.0.1:8000/projects/{project}/manual-assets"
                )
                break

        if stage == "06_render":
            status_path = root / "06_render" / "render_status.json"
            if status_path.exists():
                render_status = json.loads(status_path.read_text())
                if not render_status.get("rendered"):
                    typer.secho(
                        f"  warning: output.mp4 was not produced — {render_status.get('reason', 'see render_status.json')}",
                        fg=typer.colors.RED,
                    )

        if stage in GATED_STAGES and not state.is_approved(stage):
            typer.secho(
                f"  '{stage}' needs approval before continuing (autovid approve {project} {stage})",
                fg=typer.colors.YELLOW,
            )
            break


@app.command()
def approve(project: str, stage: str) -> None:
    """Mark a stage approved so the pipeline can continue past its gate."""
    root = _project_root(project)
    if stage not in GATED_STAGES:
        typer.secho(f"'{stage}' has no approval gate", fg=typer.colors.RED)
        raise typer.Exit(1)

    state = ProjectState(root=root)
    config = state.load_config()

    if stage == "01_research" and (config.get("video") or {}).get("high_stakes", False):
        research_md = root / "01_research" / "research.md"
        if research_md.exists() and "[UNSOURCED]" in research_md.read_text():
            typer.secho(
                "Refusing to approve: high_stakes project still has [UNSOURCED] claims in research.md",
                fg=typer.colors.RED,
            )
            raise typer.Exit(1)

    state.approve(stage)
    typer.secho(f"Approved '{stage}' for '{project}'", fg=typer.colors.GREEN)


@config_app.command("show")
def config_show(project: str) -> None:
    """Print the current provider config for every capability of a project."""
    root = _project_root(project)
    config = ProjectState(root=root).load_config()
    providers = config.get("providers", {}) or {}
    for cap in CAPABILITIES:
        cfg = providers.get(cap) or {}
        typer.echo(f"{cap}:")
        typer.echo(f"  default: {cfg.get('default')}")
        for stage, provider_id in (cfg.get("routes") or {}).items():
            typer.echo(f"  route[{stage}]: {provider_id}")
        for k, v in (cfg.get("options") or {}).items():
            typer.echo(f"  option.{k}: {v}")


@config_app.command("set")
def config_set(
    project: str,
    capability: str = typer.Argument(..., help=f"one of: {', '.join(CAPABILITIES)}"),
    provider: str = typer.Argument(..., help="<vendor>/<model>, e.g. custom/opus or gemini/gemini-2.5-flash-lite"),
    stage: str | None = typer.Option(
        None, "--stage", help="Route only this stage to the provider; omit to change the capability's default"
    ),
    option: list[str] | None = typer.Option(  # noqa: B008 — typer's own idiom for repeatable options
        None, "--option", help="key=value, repeatable — merged into providers.<capability>.options "
        "(e.g. --option base_url=http://localhost:20128/v1 --option api_key_env=NINEROUTER_API_KEY)"
    ),
) -> None:
    """Switch a capability (or one stage of it) to a different provider by editing project.yaml."""
    if capability not in CAPABILITIES:
        typer.secho(f"Unknown capability '{capability}' — one of: {', '.join(CAPABILITIES)}", fg=typer.colors.RED)
        raise typer.Exit(1)

    root = _project_root(project)
    config_path = root / "project.yaml"
    config = yaml.safe_load(config_path.read_text())
    cap_cfg = config.setdefault("providers", {}).setdefault(capability, {})

    if stage:
        cap_cfg.setdefault("routes", {})[stage] = provider
    else:
        cap_cfg["default"] = provider

    for item in option or []:
        if "=" not in item:
            typer.secho(f"Bỏ qua option không hợp lệ (cần key=value): '{item}'", fg=typer.colors.YELLOW)
            continue
        key, _, value = item.partition("=")
        cap_cfg.setdefault("options", {})[key] = _coerce_option_value(value)

    config_path.write_text(yaml.dump(config, sort_keys=False))
    target = f"stage '{stage}'" if stage else "default"
    typer.secho(f"'{capability}' {target} -> {provider}", fg=typer.colors.GREEN)


@app.command()
def ui(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Launch the local dashboard."""
    import uvicorn

    uvicorn.run("dashboard.server:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    app()
