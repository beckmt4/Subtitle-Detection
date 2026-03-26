"""Media file inspector for SubTagger.

Uses ``ffprobe`` to interrogate media containers and extract subtitle-stream
metadata without decoding any content.
"""
from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Language tag values that are considered *unknown* (i.e. need detection).
_UNKNOWN_LANG_TAGS: frozenset[str] = frozenset(
    ["", "und", "unknown", "unk", "none"]
)


@dataclass
class SubtitleStream:
    """Metadata for a single subtitle stream inside a media container."""

    index: int
    codec_name: str
    language: str | None
    title: str | None
    is_forced: bool
    is_default: bool


@dataclass
class FileInfo:
    """Aggregated metadata for a media file."""

    path: Path
    subtitle_streams: list[SubtitleStream] = field(default_factory=list)
    has_video: bool = False
    has_audio: bool = False


def is_unknown_language(lang: str | None) -> bool:
    """Return *True* when *lang* represents an absent or unknown language tag.

    Args:
        lang: ISO 639-2 / BCP-47 language code, or *None*.

    Returns:
        ``True`` when the language is absent / unknown; ``False`` when it
        holds a meaningful value.
    """
    if lang is None:
        return True
    return lang.strip().lower() in _UNKNOWN_LANG_TAGS


def _parse_streams(streams: list[dict]) -> tuple[list[SubtitleStream], bool, bool]:
    """Parse the ``streams`` array from ffprobe JSON output.

    Args:
        streams: Parsed list of stream objects from ffprobe.

    Returns:
        Tuple of ``(subtitle_streams, has_video, has_audio)``.
    """
    subtitle_streams: list[SubtitleStream] = []
    has_video = False
    has_audio = False

    for stream in streams:
        codec_type: str = stream.get("codec_type", "")

        if codec_type == "video":
            has_video = True
        elif codec_type == "audio":
            has_audio = True
        elif codec_type == "subtitle":
            tags: dict = stream.get("tags", {})
            disposition: dict = stream.get("disposition", {})

            language = tags.get("language") or None
            title = tags.get("title") or None

            subtitle_streams.append(
                SubtitleStream(
                    index=stream.get("index", 0),
                    codec_name=stream.get("codec_name", "unknown"),
                    language=language,
                    title=title,
                    is_forced=bool(disposition.get("forced", 0)),
                    is_default=bool(disposition.get("default", 0)),
                )
            )

    return subtitle_streams, has_video, has_audio


def inspect_file(path: Path) -> FileInfo:
    """Run ``ffprobe`` on *path* and return structured stream metadata.

    Args:
        path: Path to the media file to inspect.

    Returns:
        :class:`FileInfo` instance populated with stream details.  On error
        (e.g. ffprobe not installed, corrupt file), an empty
        :class:`FileInfo` is returned and the error is logged.
    """
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        str(path),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        logger.error("ffprobe not found — please install ffmpeg.")
        return FileInfo(path=path)
    except subprocess.TimeoutExpired:
        logger.error("ffprobe timed out on: %s", path)
        return FileInfo(path=path)
    except OSError as exc:
        logger.error("ffprobe OS error on %s: %s", path, exc)
        return FileInfo(path=path)

    if result.returncode != 0:
        logger.warning(
            "ffprobe returned non-zero exit code %d for %s",
            result.returncode,
            path,
        )

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse ffprobe output for %s: %s", path, exc)
        return FileInfo(path=path)

    streams_raw: list[dict] = data.get("streams", [])
    subtitle_streams, has_video, has_audio = _parse_streams(streams_raw)

    logger.debug(
        "%s — %d subtitle stream(s), video=%s, audio=%s",
        path.name,
        len(subtitle_streams),
        has_video,
        has_audio,
    )

    return FileInfo(
        path=path,
        subtitle_streams=subtitle_streams,
        has_video=has_video,
        has_audio=has_audio,
    )
