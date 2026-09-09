from __future__ import annotations

from core.providers.contracts import HealthStatus, SlideRequest, SlideResult

ID_PREFIX = "notebooklm"


class NotebookLMSlides:
    """Unofficial-library adapter — see master plan §9.6. Not the default; only
    opt in if core/providers/slides/html_renderer.py stops being enough.
    Google renamed NotebookLM -> Gemini Notebook (7/2026); expect this to break."""

    def __init__(self, model: str, options: dict):
        self.id = f"{ID_PREFIX}/{model}"
        self.model = model
        self.options = options

    def health_check(self) -> HealthStatus:
        return HealthStatus(ok=False, detail="NotebookLM adapter not implemented yet — opt-in only, see master plan §9.6")

    def render(self, req: SlideRequest) -> SlideResult:
        raise NotImplementedError("call the unofficial NotebookLM/Gemini Notebook library here")


def get_adapter(model: str, options: dict) -> NotebookLMSlides:
    return NotebookLMSlides(model, options)
