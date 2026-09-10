from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol


@dataclass
class Money:
    usd: float


@dataclass
class HealthStatus:
    ok: bool
    detail: str = ""


class ManualAssetPending(Exception):
    """Raised by a manual/* provider's generate() when it wrote generation
    instructions to disk instead of producing a real asset, and is waiting on
    a human to create the asset externally and feed it back via
    core.manual_assets. Not a failure — callers must catch this per-item and
    let the rest of the batch/run continue, not abort the whole stage."""

    def __init__(self, beat_id: str, prompt_path: str, expected_path: str, capability: str = "image"):
        self.beat_id = beat_id
        self.prompt_path = prompt_path
        self.expected_path = expected_path
        self.capability = capability
        super().__init__(f"manual {capability} asset pending for '{beat_id}'")


# ---------------------------------------------------------------- text ----

@dataclass
class TextRequest:
    prompt: str
    stage: str = ""
    system: str | None = None
    max_output_tokens: int = 4096
    temperature: float = 0.7


@dataclass
class TextResult:
    text: str
    input_tokens: int
    output_tokens: int
    model: str


class TextProvider(Protocol):
    id: str

    def estimate_cost(self, req: TextRequest) -> Money: ...
    def health_check(self) -> HealthStatus: ...
    def generate(self, req: TextRequest) -> TextResult: ...


# -------------------------------------------------------------- research ---

@dataclass
class ResearchQuery:
    query: str
    max_results: int = 5


@dataclass
class ResearchSource:
    url: str
    title: str
    snippet: str
    confidence: float = 0.5


@dataclass
class ResearchResult:
    sources: list[ResearchSource]


class ResearchProvider(Protocol):
    id: str

    def estimate_cost(self, req: ResearchQuery) -> Money: ...
    def health_check(self) -> HealthStatus: ...
    def search(self, req: ResearchQuery) -> ResearchResult: ...


# ------------------------------------------------------------------ tts ----

@dataclass
class TTSRequest:
    text: str
    out_path: str
    locale: str = "en"
    voice_id: str = ""
    rate: float = 1.0


@dataclass
class TTSResult:
    audio_path: str
    duration_sec: float
    char_count: int


class TTSProvider(Protocol):
    id: str

    def estimate_cost(self, req: TTSRequest) -> Money: ...
    def health_check(self) -> HealthStatus: ...
    def synthesize(self, req: TTSRequest) -> TTSResult: ...


# ---------------------------------------------------------------- image ----

ImageIntent = Literal["metaphor", "hero", "chapter_cover", "transition"]


@dataclass
class ImageCaps:
    resolutions: list[str] = field(default_factory=list)
    batch: bool = False
    edit: bool = False
    text_in_image: bool = False


@dataclass
class ImageRequest:
    intent: ImageIntent
    subject: str
    maps_to: str
    style_anchor: str
    out_path: str
    aspect: str = "16:9"
    no_text: bool = True


@dataclass
class ImageResult:
    image_path: str
    provider: str
    model: str


class ImageProvider(Protocol):
    id: str
    caps: ImageCaps

    def estimate_cost(self, req: ImageRequest) -> Money: ...
    def health_check(self) -> HealthStatus: ...
    def generate(self, req: ImageRequest) -> ImageResult: ...


# ----------------------------------------------------------- video_clip ----

@dataclass
class VideoClipRequest:
    prompt: str
    duration_sec: float
    out_path: str
    aspect: str = "16:9"


@dataclass
class VideoClipResult:
    clip_path: str
    duration_sec: float


class VideoClipProvider(Protocol):
    id: str

    def estimate_cost(self, req: VideoClipRequest) -> Money: ...
    def health_check(self) -> HealthStatus: ...
    def generate(self, req: VideoClipRequest) -> VideoClipResult: ...


# -------------------------------------------------------------- slides ----

@dataclass
class SlideRequest:
    template: str
    content: dict
    out_path: str
    locale: str = "en"
    size: str = ""  # "WxH" viewport override, e.g. "1280x720" — empty means the renderer's default


@dataclass
class SlideResult:
    image_path: str
    ok: bool = True
    error: str = ""


class SlideProvider(Protocol):
    id: str

    def health_check(self) -> HealthStatus: ...
    def render(self, req: SlideRequest) -> SlideResult: ...


# ------------------------------------------------------------- publish ----

@dataclass
class PublishRequest:
    video_path: str
    title: str
    description: str
    tags: list[str]
    thumbnail_path: str
    privacy: str = "private"


@dataclass
class PublishResult:
    url: str
    remote_id: str


class PublishProvider(Protocol):
    id: str

    def health_check(self) -> HealthStatus: ...
    def publish(self, req: PublishRequest) -> PublishResult: ...
