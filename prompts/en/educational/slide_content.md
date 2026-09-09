Generate the on-screen content for one slide of an educational video. The
slide's visual type is: **{{ visual_type }}**.

Narration for this beat (do not repeat it verbatim on the slide — distill it):
"{{ beat_text }}"

Return ONLY a JSON object matching the schema for `{{ visual_type }}` below,
no other text.

{% if visual_type == "code" %}
Schema: {"code": "<the code listing, newlines as \n>", "title": "<optional short label, or omit>"}
Keep the listing short enough to read on screen (under ~12 lines).
{% elif visual_type == "diagram" %}
Schema: {"svg": "<a complete, self-contained <svg>...</svg> string>", "caption": "<optional one-line caption, or omit>", "title": "<optional short label, or omit>"}
The svg must use viewBox="0 0 960 540", inline styles or attributes only (no
external CSS/fonts), a transparent or dark (#1a1d27) background, and light
text/lines (#f5f5f7 or #7c9cff) so it reads on a dark slide. Keep it simple:
a handful of boxes/arrows/labels illustrating the beat, not a detailed
technical schematic.
{% elif visual_type == "comparison" %}
Schema: {"left_title": "<short label>", "left_items": ["<point>", ...], "right_title": "<short label>", "right_items": ["<point>", ...], "title": "<optional short label, or omit>"}
2-4 items per side, each a short phrase (not a full sentence).
{% endif %}
