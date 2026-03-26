"""Ollama-based language adjudication for SubTagger.

When automated detection is uncertain, this module sends a sample of
subtitle text to a locally running Ollama instance and asks an LLM to
make a conservative language determination.
"""
from __future__ import annotations

import json
import logging

import requests

from subtagger.detector import DetectionResult, _resolve_codes

logger = logging.getLogger(__name__)

# Prompt template sent to Ollama.  ``{subtitle_text}`` is replaced at call time.
_PROMPT_TEMPLATE = """\
You are a subtitle language adjudication assistant.
Your job is to determine the most likely language of a subtitle text sample.
Rules:
- Only identify the language of the subtitle text
- Do not translate
- Do not rewrite the text
- Return unknown if evidence is weak
- Prefer conservative decisions
- Consider that subtitles may contain proper nouns, numbers, and punctuation
- Focus on function words, grammar patterns, and character sets
- If the text is too short or ambiguous, return unknown

Return JSON only in this format:
{{"language_name": "...", "iso_639_1": "...", "iso_639_2": "...", "confidence": 0.0, "reason": "..."}}

Subtitle sample:
{subtitle_text}
"""

# Maximum number of characters of subtitle text included in the prompt.
_MAX_SAMPLE_CHARS = 1500


def adjudicate_language(
    text: str,
    url: str = "http://localhost:11434",
    model: str = "llama3",
) -> DetectionResult | None:
    """Ask an Ollama LLM to identify the language of *text*.

    Sends the subtitle text sample to the ``/api/generate`` endpoint of the
    Ollama server and parses the JSON response.

    Args:
        text: Cleaned subtitle dialogue text to classify.
        url: Base URL of the Ollama API (e.g. ``"http://localhost:11434"``).
        model: Ollama model name to use (e.g. ``"llama3"``).

    Returns:
        A :class:`~subtagger.detector.DetectionResult` on success, or *None*
        when the server is unavailable or returns an unparseable response.
    """
    sample = text[:_MAX_SAMPLE_CHARS].strip()
    prompt = _PROMPT_TEMPLATE.format(subtitle_text=sample)

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
    }

    endpoint = url.rstrip("/") + "/api/generate"

    try:
        logger.debug("Sending request to Ollama at %s (model=%s).", endpoint, model)
        response = requests.post(endpoint, json=payload, timeout=60)
        response.raise_for_status()
    except requests.exceptions.ConnectionError:
        logger.warning("Cannot reach Ollama at %s — check that it is running.", url)
        return None
    except requests.exceptions.Timeout:
        logger.warning("Ollama request timed out after 60 seconds.")
        return None
    except requests.exceptions.RequestException as exc:
        logger.warning("Ollama request failed: %s", exc)
        return None

    try:
        outer = response.json()
        # The actual JSON response from the model is in the "response" field.
        raw_inner: str = outer.get("response", "")
        # raw_inner may already be a dict when format=json is honoured.
        if isinstance(raw_inner, dict):
            inner = raw_inner
        else:
            inner = json.loads(raw_inner)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Could not parse Ollama JSON response: %s", exc)
        return None

    lang_name: str = str(inner.get("language_name", "unknown")).lower().strip()
    iso1: str = str(inner.get("iso_639_1", "und")).lower().strip()
    iso2: str = str(inner.get("iso_639_2", "und")).lower().strip()
    confidence: float = 0.0

    try:
        confidence = float(inner.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0

    if lang_name == "unknown" or (iso1 in ("und", "") and iso2 in ("und", "")):
        logger.info("Ollama returned unknown language for the supplied sample.")
        return DetectionResult(
            language_name="unknown",
            iso_639_1="und",
            iso_639_2="und",
            confidence=0.0,
            method="ollama",
        )

    # If the model omitted one of the codes, try to fill it in from our map.
    if iso2 in ("und", "") or iso1 in ("und", ""):
        resolved1, resolved2 = _resolve_codes(lang_name)
        if iso1 in ("und", ""):
            iso1 = resolved1
        if iso2 in ("und", ""):
            iso2 = resolved2

    reason: str = str(inner.get("reason", ""))
    logger.info(
        "Ollama adjudication: %s (%.2f%%) — %s", lang_name, confidence * 100, reason
    )

    return DetectionResult(
        language_name=lang_name,
        iso_639_1=iso1,
        iso_639_2=iso2,
        confidence=confidence,
        method="ollama",
    )
