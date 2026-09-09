from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from core.providers.contracts import HealthStatus, SlideRequest, SlideResult

TEMPLATES_DIR = Path(__file__).resolve().parents[3] / "templates" / "slides"
ID = "local/html_renderer"


class HTMLSlideRenderer:
    id = ID

    def __init__(self, options: dict):
        self.options = options
        self.env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))

    def health_check(self) -> HealthStatus:
        try:
            import playwright  # noqa: F401
        except ImportError:
            return HealthStatus(ok=False, detail="playwright not installed — pip install playwright && playwright install chromium")
        return HealthStatus(ok=True)

    def render(self, req: SlideRequest) -> SlideResult:
        template = self.env.get_template(f"{req.template}.html")
        html = template.render(**req.content)

        out_path = Path(req.out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        html_path = out_path.with_suffix(".html")
        html_path.write_text(html)

        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page(viewport={"width": 1920, "height": 1080})
                page.goto(html_path.as_uri())
                page.screenshot(path=str(out_path))
                browser.close()
        except Exception as e:  # noqa: BLE001 — degrade to an empty PNG rather than crash the pipeline,
            # but the caller must be told: an empty slide is a silent content
            # gap otherwise (see plan/phase-3-first-video.md §3.1).
            out_path.write_bytes(b"")
            return SlideResult(image_path=str(out_path), ok=False, error=str(e))

        return SlideResult(image_path=str(out_path))


def get_adapter(model: str, options: dict) -> HTMLSlideRenderer:
    return HTMLSlideRenderer(options)
