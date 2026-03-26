"""Language detector for SubTagger.

Uses *lingua* as the primary detector and falls back to *langdetect* when
lingua is not installed.  Detection results are normalised to ISO 639-1 and
ISO 639-2 codes.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Language code mapping
# iso_name → (iso_639_1, iso_639_2)
# ---------------------------------------------------------------------------
_LANG_MAP: dict[str, tuple[str, str]] = {
    "afrikaans": ("af", "afr"),
    "albanian": ("sq", "sqi"),
    "arabic": ("ar", "ara"),
    "armenian": ("hy", "hye"),
    "azerbaijani": ("az", "aze"),
    "basque": ("eu", "eus"),
    "belarusian": ("be", "bel"),
    "bengali": ("bn", "ben"),
    "bosnian": ("bs", "bos"),
    "bulgarian": ("bg", "bul"),
    "catalan": ("ca", "cat"),
    "chinese": ("zh", "zho"),
    "croatian": ("hr", "hrv"),
    "czech": ("cs", "ces"),
    "danish": ("da", "dan"),
    "dutch": ("nl", "nld"),
    "english": ("en", "eng"),
    "esperanto": ("eo", "epo"),
    "estonian": ("et", "est"),
    "finnish": ("fi", "fin"),
    "french": ("fr", "fra"),
    "galician": ("gl", "glg"),
    "georgian": ("ka", "kat"),
    "german": ("de", "deu"),
    "greek": ("el", "ell"),
    "gujarati": ("gu", "guj"),
    "haitian creole": ("ht", "hat"),
    "hebrew": ("he", "heb"),
    "hindi": ("hi", "hin"),
    "hungarian": ("hu", "hun"),
    "icelandic": ("is", "isl"),
    "indonesian": ("id", "ind"),
    "irish": ("ga", "gle"),
    "italian": ("it", "ita"),
    "japanese": ("ja", "jpn"),
    "kannada": ("kn", "kan"),
    "kazakh": ("kk", "kaz"),
    "korean": ("ko", "kor"),
    "latin": ("la", "lat"),
    "latvian": ("lv", "lav"),
    "lithuanian": ("lt", "lit"),
    "macedonian": ("mk", "mkd"),
    "malay": ("ms", "msa"),
    "maltese": ("mt", "mlt"),
    "marathi": ("mr", "mar"),
    "mongolian": ("mn", "mon"),
    "nepali": ("ne", "nep"),
    "norwegian": ("no", "nor"),
    "norwegian bokmal": ("nb", "nob"),
    "norwegian nynorsk": ("nn", "nno"),
    "panjabi": ("pa", "pan"),
    "persian": ("fa", "fas"),
    "polish": ("pl", "pol"),
    "portuguese": ("pt", "por"),
    "romanian": ("ro", "ron"),
    "russian": ("ru", "rus"),
    "serbian": ("sr", "srp"),
    "sinhala": ("si", "sin"),
    "slovak": ("sk", "slk"),
    "slovenian": ("sl", "slv"),
    "somali": ("so", "som"),
    "spanish": ("es", "spa"),
    "swahili": ("sw", "swa"),
    "swedish": ("sv", "swe"),
    "tagalog": ("tl", "tgl"),
    "tamil": ("ta", "tam"),
    "telugu": ("te", "tel"),
    "thai": ("th", "tha"),
    "turkish": ("tr", "tur"),
    "ukrainian": ("uk", "ukr"),
    "urdu": ("ur", "urd"),
    "uzbek": ("uz", "uzb"),
    "vietnamese": ("vi", "vie"),
    "welsh": ("cy", "cym"),
    "yoruba": ("yo", "yor"),
    "zulu": ("zu", "zul"),
}

@dataclass
class DetectionResult:
    """Result of a language detection attempt."""

    language_name: str
    iso_639_1: str
    iso_639_2: str
    confidence: float
    method: str


def _unknown_result(method: str = "none") -> DetectionResult:
    return DetectionResult(
        language_name="unknown",
        iso_639_1="und",
        iso_639_2="und",
        confidence=0.0,
        method=method,
    )


def _resolve_codes(language_name: str) -> tuple[str, str]:
    """Look up ISO 639-1 and ISO 639-2 codes for a language name.

    The lookup is case-insensitive.  If the name is not found in the built-in
    mapping, ``("und", "und")`` is returned.
    """
    key = language_name.lower().strip()
    codes = _LANG_MAP.get(key)
    if codes:
        return codes
    # Partial match as a last resort.
    for name, pair in _LANG_MAP.items():
        if key in name or name in key:
            return pair
    return ("und", "und")


# ---------------------------------------------------------------------------
# Lingua-based detection
# ---------------------------------------------------------------------------

def _detect_with_lingua(text: str, min_confidence: float) -> DetectionResult | None:
    """Attempt language detection using the *lingua* library.

    Returns *None* when lingua is not installed or detection is inconclusive.
    """
    try:
        from lingua import LanguageDetectorBuilder  # type: ignore[import]
    except ImportError:
        logger.debug("lingua not available; skipping.")
        return None

    try:
        detector = LanguageDetectorBuilder.from_all_languages().build()
        result = detector.detect_language_of(text)

        if result is None:
            return None

        # lingua's confidence_values() returns a list of ConfidenceValue objects.
        confidence_values = detector.compute_language_confidence_values(text)
        confidence: float = 0.0
        for cv in confidence_values:
            if cv.language == result:
                confidence = cv.value
                break

        if confidence < min_confidence:
            logger.debug(
                "lingua confidence %.3f below threshold %.3f for %s",
                confidence,
                min_confidence,
                result.name,
            )
            return None

        lang_name = result.name.lower().replace("_", " ")
        iso1, iso2 = _resolve_codes(lang_name)

        return DetectionResult(
            language_name=lang_name,
            iso_639_1=iso1,
            iso_639_2=iso2,
            confidence=confidence,
            method="lingua",
        )

    except Exception as exc:  # noqa: BLE001
        logger.warning("lingua detection error: %s", exc)
        return None


# ---------------------------------------------------------------------------
# langdetect-based detection
# ---------------------------------------------------------------------------

def _detect_with_langdetect(text: str, min_confidence: float) -> DetectionResult | None:
    """Attempt language detection using the *langdetect* library.

    Returns *None* when langdetect is not installed or detection is
    inconclusive.
    """
    try:
        from langdetect import detect_langs  # type: ignore[import]
        from langdetect.lang_detect_exception import LangDetectException  # type: ignore[import]
    except ImportError:
        logger.debug("langdetect not available; skipping.")
        return None

    try:
        probabilities = detect_langs(text)
        if not probabilities:
            return None

        best = probabilities[0]
        confidence: float = best.prob

        if confidence < min_confidence:
            logger.debug(
                "langdetect confidence %.3f below threshold %.3f",
                confidence,
                min_confidence,
            )
            return None

        # langdetect returns ISO 639-1 codes directly.
        iso1 = best.lang
        # Reverse-look up the language name from iso1.
        lang_name = "unknown"
        iso2 = "und"
        for name, (code1, code2) in _LANG_MAP.items():
            if code1 == iso1:
                lang_name = name
                iso2 = code2
                break

        if lang_name == "unknown":
            iso2 = "und"

        return DetectionResult(
            language_name=lang_name,
            iso_639_1=iso1,
            iso_639_2=iso2,
            confidence=confidence,
            method="langdetect",
        )

    except Exception as exc:  # noqa: BLE001
        logger.warning("langdetect detection error: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_language(text: str, min_confidence: float = 0.85) -> DetectionResult:
    """Detect the language of *text*.

    Tries *lingua* first, then falls back to *langdetect*.  Returns an
    "unknown" result when neither library produces a confident answer.

    Args:
        text: Cleaned subtitle dialogue text.
        min_confidence: Minimum acceptable detection confidence in [0, 1].

    Returns:
        A :class:`DetectionResult` instance.
    """
    if not text or not text.strip():
        logger.debug("Empty text supplied to detect_language.")
        return _unknown_result("empty_input")

    result = _detect_with_lingua(text, min_confidence)
    if result is not None:
        logger.info(
            "Language detected: %s (%.2f%%) via %s",
            result.language_name,
            result.confidence * 100,
            result.method,
        )
        return result

    result = _detect_with_langdetect(text, min_confidence)
    if result is not None:
        logger.info(
            "Language detected: %s (%.2f%%) via %s",
            result.language_name,
            result.confidence * 100,
            result.method,
        )
        return result

    logger.info("Language detection inconclusive for supplied text.")
    return _unknown_result("no_library")
