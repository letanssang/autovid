Classify the on-screen visual for each narration beat below, in one batch, for
an educational YouTube video.

Visual types (pick exactly one per beat):
- `title` — a short text-only title/key-point card. Good for openers, section headers, one-line takeaways.
- `code` — a code listing. Only when the beat narrates or refers to actual code/syntax.
- `diagram` — a simple SVG diagram (boxes, arrows, flow). Only when the beat describes a process, architecture, or relationship that benefits from a drawing.
- `comparison` — a two-column comparison (e.g. "before vs after", "X vs Y"). Only when the beat is explicitly contrasting two things.
- `ai_image` — a generated illustrative image. Use for abstract or evocative moments where a picture adds value and none of the above fit.
- `b_roll` — no strong visual need; the beat's own narration will be shown as a pull-quote. The safe default when nothing else clearly fits.

Rules:
- Avoid picking the same type as the immediately preceding beat (including across beats in this batch).
- Only choose `ai_image` if it clearly earns its cost — this video's remaining AI-image budget is {{ remaining_ai_images }}. If the budget is 0, never choose `ai_image`.
- The type immediately before this batch's first beat was: {{ previous_visual_type or "(none — this is the first beat)" }}.

Beats (narration text, in order):
{% for beat in beats %}
{{ loop.index0 }}. "{{ beat.text }}"
{% endfor %}

Respond with ONLY a JSON array, one object per beat in the same order, no
other text:
[{"index": 0, "visual_type": "...", "reason": "one short phrase a human reviewer can read"}, ...]
