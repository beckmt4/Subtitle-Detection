"""Subtitle text cleaner for SubTagger.

Strips all non-dialogue content from raw subtitle text so that only the
spoken words (or their written equivalent) remain for language detection.
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Pre-compiled regular expressions
# ---------------------------------------------------------------------------

# SRT sequence numbers – lines that consist entirely of one or more digits.
_RE_SEQUENCE = re.compile(r"^\d+\s*$", re.MULTILINE)

# SRT / VTT timestamp lines.
_RE_SRT_TIMESTAMP = re.compile(
    r"\d{1,2}:\d{2}:\d{2}[,\.]\d{3}\s*-->\s*\d{1,2}:\d{2}:\d{2}[,\.]\d{3}[^\n]*",
    re.MULTILINE,
)

# VTT file header (the "WEBVTT" preamble and any header block).
_RE_VTT_HEADER = re.compile(
    r"^WEBVTT.*?(\n\n|\Z)",
    re.DOTALL | re.MULTILINE,
)

# VTT cue identifiers (optional text label before a timestamp line).
_RE_VTT_CUE_ID = re.compile(r"^[^\n]+\n(?=\d{2}:\d{2})", re.MULTILINE)

# ASS / SSA section headers and metadata lines.
_RE_ASS_SECTION = re.compile(
    r"^\[.*?\]\s*\n(.*?\n)*?(?=\[|\Z)",
    re.MULTILINE | re.DOTALL,
)
# ASS "Dialogue:" lines – extract only the text component (field 10+).
_RE_ASS_DIALOGUE = re.compile(
    r"^(?:Dialogue|Comment):.*?,.*?,.*?,.*?,.*?,.*?,.*?,.*?,.*?,(.*)",
    re.MULTILINE,
)
# ASS override tags  e.g. {\an8}  {\i1}  {\pos(320,240)}
_RE_ASS_OVERRIDE = re.compile(r"\{[^}]*\}")

# ASS hard-line-break tag.
_RE_ASS_LINEBREAK = re.compile(r"\\N", re.IGNORECASE)

# HTML tags.
_RE_HTML = re.compile(r"<[^>]+>")

# SDH noise: square-bracket descriptions and round-bracket stage directions.
_RE_SDH_SQUARE = re.compile(r"\[[^\]]*\]")
_RE_SDH_ROUND = re.compile(r"\([^)]*\)")

# Collapse runs of whitespace / blank lines.
_RE_BLANK_LINES = re.compile(r"\n{3,}")
_RE_TRAILING_SPACES = re.compile(r"[ \t]+$", re.MULTILINE)


def _is_ass_format(text: str) -> bool:
    """Heuristic: return *True* when *text* looks like an ASS / SSA file."""
    first_500 = text[:500]
    return "[Script Info]" in first_500 or "[Events]" in first_500


def _is_vtt_format(text: str) -> bool:
    """Heuristic: return *True* when *text* looks like a WebVTT file."""
    return text.lstrip().startswith("WEBVTT")


def _clean_ass(text: str) -> str:
    """Extract dialogue lines from an ASS / SSA document."""
    lines = _RE_ASS_DIALOGUE.findall(text)
    if not lines:
        # Fall through to generic cleaning when no Dialogue: lines found.
        return text
    joined = "\n".join(lines)
    # Remove ASS override tags and hard-line-breaks.
    joined = _RE_ASS_OVERRIDE.sub("", joined)
    joined = _RE_ASS_LINEBREAK.sub("\n", joined)
    return joined


def clean_subtitle_text(raw_text: str, remove_sdh: bool = True) -> str:
    """Clean *raw_text* to retain only dialogue words.

    Processing steps (applied in order):

    1. Handle format-specific markup (ASS/SSA full parse; VTT header strip).
    2. Remove timestamp lines.
    3. Remove sequence numbers.
    4. Remove HTML tags.
    5. Remove ASS override tags (if any remain).
    6. Optionally remove SDH noise (``[music]``, ``(applause)`` etc.).
    7. Normalise whitespace.

    Args:
        raw_text: Raw subtitle file contents (any supported format).
        remove_sdh: When *True*, strip bracketed / parenthesised annotations
                    that describe sound effects and background noise.

    Returns:
        Cleaned dialogue text.
    """
    if not raw_text:
        return ""

    text = raw_text

    if _is_ass_format(text):
        text = _clean_ass(text)
    else:
        if _is_vtt_format(text):
            # Strip the WEBVTT header block.
            text = _RE_VTT_HEADER.sub("", text, count=1)
            # Strip optional cue identifiers.
            text = _RE_VTT_CUE_ID.sub("", text)

        # Remove timestamp lines (works for both SRT and VTT).
        text = _RE_SRT_TIMESTAMP.sub("", text)

        # Remove bare sequence numbers.
        text = _RE_SEQUENCE.sub("", text)

    # Remove any remaining ASS override tags.
    text = _RE_ASS_OVERRIDE.sub("", text)

    # Remove HTML tags (common in SRT files).
    text = _RE_HTML.sub("", text)

    if remove_sdh:
        text = _RE_SDH_SQUARE.sub("", text)
        text = _RE_SDH_ROUND.sub("", text)

    # Normalise whitespace.
    text = _RE_TRAILING_SPACES.sub("", text)
    text = _RE_BLANK_LINES.sub("\n\n", text)
    text = text.strip()

    return text
