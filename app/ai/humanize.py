"""Deterministic cleanup of AI writing tells that prompt rules don't reliably remove.

Models overuse the em dash (—) and en dash (–) as sentence punctuation, and a single prompt
instruction rarely stops it. We strip them from generated free text as a belt-and-suspenders guard
alongside the prompt rules in tailor.py / form_agent.py. Numeric ranges (e.g. 200–300) are kept.
"""
from __future__ import annotations

import re

# Em/en dash used as punctuation (not inside a numeric range) -> comma.
_DASH = re.compile(r"(?<!\d)\s*[—–]\s*(?!\d)")


def strip_ai_dashes(text: str) -> str:
    """Replace em/en dashes used as punctuation with a comma; keep numeric ranges intact."""
    if not text:
        return text
    out = _DASH.sub(", ", text)
    out = re.sub(r",\s*,", ", ", out)      # collapse doubled commas from paired dashes
    out = re.sub(r"\s+,", ",", out)        # no space before a comma
    out = re.sub(r"[ \t]{2,}", " ", out)   # collapse runs of spaces
    return out.strip()
