Write YouTube metadata for an educational video on "{{ topic }}".

Video outline (chapter and section titles):
{{ outline_summary }}

Key sources referenced during research:
{{ sources_summary }}

Respond with a JSON object with exactly these keys:
- "title": a compelling YouTube title, at most 70 characters, accurately describing the video —
  no clickbait, no ALL CAPS, no emoji.
- "description": 2-3 paragraphs of plain text (no markdown) summarizing what the viewer will learn
  and why it matters. Do not include chapter timestamps or a sources list — those are appended
  automatically after your text.
- "tags": a JSON array of 10-15 relevant search tags (single words or short phrases, no "#", no duplicates).

Respond with JSON only, no other text.
