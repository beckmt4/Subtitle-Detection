"""File-system scanner for SubTagger.

Recursively walks one or more root directories and collects paths that
match the configured include/exclude rules.
"""
from __future__ import annotations

import fnmatch
import logging
from pathlib import Path

from subtagger.config import Config

logger = logging.getLogger(__name__)

# Extensions considered to be standalone subtitle files (not wrapped in a
# media container).
_SUBTITLE_EXTENSIONS: frozenset[str] = frozenset([".srt", ".ass", ".ssa", ".vtt"])


def _is_excluded(path: Path, patterns: list[str]) -> bool:
    """Return *True* when *path* matches any of the glob *patterns*."""
    path_str = str(path)
    for pattern in patterns:
        if fnmatch.fnmatch(path_str, pattern):
            return True
        # Also test against just the filename so simple patterns like
        # "*trailer*" work without a full-path prefix.
        if fnmatch.fnmatch(path.name, pattern):
            return True
    return False


def scan_paths(paths: list[str], config: Config) -> list[Path]:
    """Scan *paths* and return all matching media / subtitle files.

    Both directory paths and individual file paths are accepted.  Directories
    are walked recursively.  Files are included when:

    * Their suffix (case-insensitive) is in ``config.include_extensions``.
    * None of ``config.exclude_patterns`` match the file path.

    Args:
        paths: List of file or directory path strings to scan.
        config: Active :class:`~subtagger.config.Config` instance.

    Returns:
        Deduplicated list of :class:`~pathlib.Path` objects for every
        qualifying file found.
    """
    extensions: frozenset[str] = frozenset(
        ext.lower() for ext in config.include_extensions
    )
    exclude_patterns: list[str] = config.exclude_patterns or []

    seen: set[Path] = set()
    results: list[Path] = []

    for raw_path in paths:
        root = Path(raw_path)

        if not root.exists():
            logger.warning("Scan path does not exist: %s", root)
            continue

        if root.is_file():
            candidates = [root]
        else:
            logger.info("Scanning directory: %s", root)
            candidates = list(root.rglob("*"))

        for candidate in candidates:
            if not candidate.is_file():
                continue

            if candidate.suffix.lower() not in extensions:
                continue

            if _is_excluded(candidate, exclude_patterns):
                logger.debug("Excluded by pattern: %s", candidate)
                continue

            resolved = candidate.resolve()
            if resolved in seen:
                continue

            seen.add(resolved)
            results.append(candidate)
            logger.debug("Found: %s", candidate)

    logger.info(
        "Scan complete — %d file(s) found across %d path(s).",
        len(results),
        len(paths),
    )
    return results


def split_media_and_subtitles(
    paths: list[Path],
) -> tuple[list[Path], list[Path]]:
    """Partition *paths* into (media_files, external_subtitle_files).

    Args:
        paths: Mixed list of file paths returned by :func:`scan_paths`.

    Returns:
        A 2-tuple ``(media_files, subtitle_files)`` where *media_files*
        contains container files (e.g. ``.mkv``, ``.mp4``) and
        *subtitle_files* contains bare subtitle files (e.g. ``.srt``).
    """
    media: list[Path] = []
    subtitles: list[Path] = []

    for p in paths:
        if p.suffix.lower() in _SUBTITLE_EXTENSIONS:
            subtitles.append(p)
        else:
            media.append(p)

    return media, subtitles
