from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def render_prompt(locale: str, fmt: str, name: str, **context) -> str:
    """Renders prompts/<locale>/<fmt>/<name>.md — prompts never live in Python f-strings.

    `fmt` is the video format (e.g. "educational"). New formats (narrative, listicle,
    review, ...) are added as sibling directories under prompts/<locale>/ without
    touching stage code — see project.yaml's top-level `format` field.
    """
    env = Environment(loader=FileSystemLoader(str(PROMPTS_DIR / locale / fmt)))
    template = env.get_template(f"{name}.md")
    return template.render(**context)
