"""Subtitle language tag writer for SubTagger.

Writes detected language codes back to media containers or renames external
subtitle files to embed the language code in the filename.  Supports MKV
(via ``mkvpropedit``), MP4 (via ``ffmpeg``), and external subtitle files.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from subtagger.inspector import is_unknown_language

logger = logging.getLogger(__name__)

# Suffixes handled as external subtitle files.
_SUBTITLE_SUFFIXES: frozenset[str] = frozenset([".srt", ".ass", ".ssa", ".vtt"])


# ---------------------------------------------------------------------------
# MKV
# ---------------------------------------------------------------------------

def _write_mkv(path: Path, stream_index: int, lang: str, dry_run: bool) -> bool:
    """Use ``mkvpropedit`` to set the language tag on an MKV subtitle track."""
    if dry_run:
        logger.info(
            "[DRY-RUN] Would set MKV stream %d language to '%s' in %s",
            stream_index,
            lang,
            path,
        )
        return True

    cmd = [
        "mkvpropedit",
        str(path),
        "--edit", f"track:s{stream_index + 1}",  # mkvpropedit uses 1-based subtitle track number
        "--set", f"language={lang}",
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            logger.info("MKV language tag updated: stream %d → '%s' in %s", stream_index, lang, path)
            return True
        logger.error(
            "mkvpropedit failed (exit %d) for %s: %s",
            result.returncode,
            path,
            result.stderr[:300],
        )
        return False
    except FileNotFoundError:
        logger.error("mkvpropedit not found — please install mkvtoolnix.")
        return False
    except subprocess.TimeoutExpired:
        logger.error("mkvpropedit timed out for %s", path)
        return False
    except OSError as exc:
        logger.error("OS error running mkvpropedit on %s: %s", path, exc)
        return False


# ---------------------------------------------------------------------------
# MP4
# ---------------------------------------------------------------------------

def _write_mp4(path: Path, stream_index: int, lang: str, dry_run: bool) -> bool:
    """Use ``ffmpeg`` to add / update the language metadata on an MP4 track.

    MP4 language updates require a full remux, so this operation creates a
    new file and replaces the original.
    """
    logger.warning(
        "MP4 language tagging requires a full remux — this may take a while: %s", path
    )

    if dry_run:
        logger.info(
            "[DRY-RUN] Would remux %s to set stream %d language to '%s'",
            path,
            stream_index,
            lang,
        )
        return True

    tmp_path = path.with_suffix(".subtagger_tmp.mp4")
    cmd = [
        "ffmpeg",
        "-y",
        "-v", "quiet",
        "-i", str(path),
        "-map", "0",
        "-c", "copy",
        f"-metadata:s:{stream_index}", f"language={lang}",
        str(tmp_path),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0 or not tmp_path.exists():
            logger.error(
                "ffmpeg remux failed (exit %d) for %s: %s",
                result.returncode,
                path,
                result.stderr[:300],
            )
            if tmp_path.exists():
                tmp_path.unlink()
            return False

        # Replace the original file.
        shutil.move(str(tmp_path), str(path))
        logger.info("MP4 language tag updated: stream %d → '%s' in %s", stream_index, lang, path)
        return True

    except FileNotFoundError:
        logger.error("ffmpeg not found — cannot update MP4 language tags.")
        return False
    except subprocess.TimeoutExpired:
        logger.error("ffmpeg timed out during MP4 remux of %s", path)
        return False
    except OSError as exc:
        logger.error("OS error during MP4 remux of %s: %s", path, exc)
        return False
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


# ---------------------------------------------------------------------------
# External subtitle files
# ---------------------------------------------------------------------------

def _write_external_subtitle(path: Path, lang_iso_639_1: str, dry_run: bool) -> bool:
    """Rename an external subtitle file to embed the language code.

    Example: ``movie.srt`` → ``movie.en.srt``

    If the file already has a two-letter language code stem (e.g.
    ``movie.en.srt``), it is left unchanged.
    """
    # Parse existing stems to detect an already-present language code.
    suffixes = path.suffixes  # e.g. ['.en', '.srt']
    if len(suffixes) >= 2:
        possible_lang = suffixes[-2].lstrip(".")
        if len(possible_lang) == 2 and possible_lang.isalpha():
            if not is_unknown_language(possible_lang):
                logger.info(
                    "External subtitle already has language code '%s': %s",
                    possible_lang,
                    path,
                )
                return True

    new_name = path.stem.rstrip(".") + f".{lang_iso_639_1}{path.suffix}"
    new_path = path.parent / new_name

    if dry_run:
        logger.info("[DRY-RUN] Would rename %s → %s", path.name, new_name)
        return True

    try:
        path.rename(new_path)
        logger.info("Renamed subtitle: %s → %s", path.name, new_name)
        return True
    except OSError as exc:
        logger.error("Failed to rename %s → %s: %s", path, new_path, exc)
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def write_language_tag(
    path: Path,
    stream_index: int,
    lang_iso_639_2: str,
    dry_run: bool,
    lang_iso_639_1: str = "",
) -> bool:
    """Write a language tag to a media stream or rename an external subtitle.

    The operation chosen depends on the file type:

    * ``.mkv`` — uses ``mkvpropedit`` to update the subtitle track metadata.
    * ``.mp4`` — uses ``ffmpeg`` to remux with updated stream metadata.
    * External subtitle (``.srt`` / ``.ass`` / ``.ssa`` / ``.vtt``) — renames
      the file to include the ISO 639-1 language code.

    The function is a no-op (returns ``True``) when *dry_run* is ``True``; it
    only logs what *would* happen.

    Args:
        path: Path to the file to modify.
        stream_index: Zero-based stream index (used for container formats).
        lang_iso_639_2: ISO 639-2 (three-letter) language code to write.
        dry_run: When *True*, log intended actions without making changes.
        lang_iso_639_1: ISO 639-1 (two-letter) code — used when renaming
                        external subtitle files.  Falls back to the first two
                        characters of *lang_iso_639_2* when empty.

    Returns:
        ``True`` on success (or dry-run), ``False`` on failure.
    """
    suffix = path.suffix.lower()

    if not lang_iso_639_1:
        lang_iso_639_1 = lang_iso_639_2[:2] if lang_iso_639_2 not in ("und", "") else "und"

    if suffix == ".mkv":
        return _write_mkv(path, stream_index, lang_iso_639_2, dry_run)

    if suffix == ".mp4":
        return _write_mp4(path, stream_index, lang_iso_639_2, dry_run)

    if suffix in _SUBTITLE_SUFFIXES:
        return _write_external_subtitle(path, lang_iso_639_1, dry_run)

    logger.warning("Unsupported file type for language tagging: %s", path.suffix)
    return False
