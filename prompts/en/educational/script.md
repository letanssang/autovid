Write the narration script for one section of an educational YouTube video.

Section title: {{ section_title }}
Target duration: {{ target_duration_sec }} seconds (~{{ target_word_count }} words at conversational pace)

Research notes:
{{ research }}

Knowledge spine so far (facts/terms already introduced — stay consistent, don't redefine):
{{ spine }}
{% if length_instruction %}

Your previous draft was {{ previous_word_count }} words:
"""
{{ previous_draft }}
"""
{{ length_instruction }}
{% endif %}

Write plain spoken narration only, no stage directions, no markdown, no headers.
End with one line starting exactly with "KEY_TERMS:" followed by 2-3 comma-separated
terms or facts this section introduces, for continuity tracking only — it will be
stripped before narration and must never be read aloud.
