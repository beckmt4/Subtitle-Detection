"""Subtitle text extractor for SubTagger.

Pulls raw subtitle text out of media containers (via ffmpeg) or reads
standalone subtitle files directly from disk.
"""
from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Subtitle codecs that can be dumped directly as plain text.
_TEXT_CODECS: frozenset[str] = frozenset(
    ["subrip", "srt", "ass", "ssa", "webvtt", "vtt", "mov_text", "text"]
)


def extract_subtitle_text(
    path: Path,
    stream_index: int,
    codec: str,
) -> str | None:
    """Extract raw subtitle text from a media container stream.

    Uses ``ffmpeg`` to copy the subtitle stream into a temporary file, reads
    the file, then removes it.

    Args:
        path: Path to the source media file.
        stream_index: Zero-based index of the subtitle stream inside the
                      container (as reported by ffprobe).
        codec: Codec name of the stream (e.g. ``"subrip"``, ``"ass"``).

    Returns:
        Raw subtitle text as a string, or *None* when extraction fails.
    """
    codec_lower = codec.lower()

    # Decide output format for the temporary file.
    if codec_lower in ("ass", "ssa"):
        suffix = ".ass"
    elif codec_lower in ("webvtt", "vtt"):
        suffix = ".vtt"
    else:
        suffix = ".srt"

    # Use a named temp file in the current working directory to comply with
    # environment restrictions.
    tmp_path = Path(f"._subtagger_tmp_{os.getpid()}_{stream_index}{suffix}")

    try:
        cmd = [
            "ffmpeg",
            "-y",
            "-v", "quiet",
            "-i", str(path),
            "-map", f"0:{stream_index}",
            "-c:s", "copy",
            str(tmp_path),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        if result.returncode != 0:
            logger.warning(
                "ffmpeg failed (exit %d) extracting stream %d from %s: %s",
                result.returncode,
                stream_index,
                path,
                result.stderr[:300],
            )
            return None

        if not tmp_path.exists() or tmp_path.stat().st_size == 0:
            logger.warning(
                "ffmpeg produced empty output for stream %d of %s",
                stream_index,
                path,
            )
            return None

        text = tmp_path.read_text(encoding="utf-8", errors="replace")
        logger.debug(
            "Extracted %d chars from stream %d of %s", len(text), stream_index, path
        )
        return text

    except FileNotFoundError:
        logger.error("ffmpeg not found — please install ffmpeg.")
        return None
    except subprocess.TimeoutExpired:
        logger.error("ffmpeg timed out extracting stream %d from %s", stream_index, path)
        return None
    except OSError as exc:
        logger.error("OS error during extraction of %s: %s", path, exc)
        return None
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def read_external_subtitle(path: Path) -> str | None:
    """Read a standalone subtitle file from disk.

    Supports ``.srt``, ``.ass``, ``.ssa``, and ``.vtt`` files.

    Args:
        path: Path to the subtitle file.

    Returns:
        File contents as a string, or *None* on failure.
    """
    supported = frozenset([".srt", ".ass", ".ssa", ".vtt"])
    if path.suffix.lower() not in supported:
        logger.warning("Unsupported subtitle extension: %s", path.suffix)
        return None

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        logger.debug("Read %d chars from external subtitle: %s", len(text), path)
        return text
    except OSError as exc:
        logger.error("Could not read external subtitle %s: %s", path, exc)
        return None
