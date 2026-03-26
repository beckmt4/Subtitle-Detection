"""Command-line interface for SubTagger.

Entry point: ``subtagger`` (defined in setup.py console_scripts).
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from subtagger import __version__
from subtagger.config import load_config
from subtagger.scanner import scan_paths, split_media_and_subtitles
from subtagger.inspector import inspect_file, is_unknown_language
from subtagger.extractor import extract_subtitle_text, read_external_subtitle
from subtagger.cleaner import clean_subtitle_text
from subtagger.detector import detect_language
from subtagger.writer import write_language_tag
from subtagger.reporter import AuditLog, print_summary, setup_logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="subtagger",
        description=(
            "SubTagger — automatically detect and tag subtitle language tracks "
            "in media files."
        ),
    )
    parser.add_argument(
        "paths",
        nargs="*",
        metavar="PATH",
        help="One or more files or directories to scan.",
    )
    parser.add_argument(
        "--config",
        metavar="FILE",
        default=None,
        help="Path to YAML config file (default: config.yml).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=None,
        help="Log what would be done without making any changes.",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        default=None,
        help="Detect and report languages without writing tags.",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        metavar="FLOAT",
        default=None,
        help="Minimum detection confidence threshold (0–1, default 0.85).",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        default=None,
        dest="watch_mode",
        help="Re-scan at regular intervals (watch mode).",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=None,
        dest="log_level",
        help="Logging verbosity level.",
    )
    parser.add_argument(
        "--no-whisper",
        action="store_true",
        default=False,
        help="Disable Whisper audio-transcription fallback.",
    )
    parser.add_argument(
        "--no-ollama",
        action="store_true",
        default=False,
        help="Disable Ollama LLM adjudication.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"SubTagger {__version__}",
    )
    return parser


# ---------------------------------------------------------------------------
# Core processing
# ---------------------------------------------------------------------------

def _process_media_file(path: Path, config, audit: AuditLog) -> int:
    """Inspect a media container, detect and tag unknown subtitle streams.

    Returns the number of streams that were successfully tagged.
    """
    tagged = 0
    file_info = inspect_file(path)

    for stream in file_info.subtitle_streams:
        if not is_unknown_language(stream.language):
            logger.debug(
                "Stream %d of %s already has language '%s' — skipping.",
                stream.index,
                path.name,
                stream.language,
            )
            audit.log_action(
                file_path=str(path),
                stream_index=stream.index,
                original_lang=stream.language,
                action="skipped_existing_tag",
                reason=f"Already tagged as '{stream.language}'",
            )
            continue

        logger.info("Processing stream %d of %s …", stream.index, path.name)
        raw_text = extract_subtitle_text(path, stream.index, stream.codec_name)

        if not raw_text:
            logger.warning(
                "Could not extract text from stream %d of %s.", stream.index, path.name
            )
            # Try Whisper fallback if enabled.
            if config.use_whisper_fallback:
                from subtagger.whisper_fallback import transcribe_audio
                raw_text = transcribe_audio(path, config.whisper_model)

        if not raw_text:
            audit.log_action(
                file_path=str(path),
                stream_index=stream.index,
                original_lang=stream.language,
                action="error",
                reason="Could not extract subtitle text.",
            )
            continue

        clean_text = clean_subtitle_text(raw_text)

        if len(clean_text) < config.min_text_length:
            logger.warning(
                "Cleaned text too short (%d chars) for stream %d of %s.",
                len(clean_text),
                stream.index,
                path.name,
            )
            audit.log_action(
                file_path=str(path),
                stream_index=stream.index,
                original_lang=stream.language,
                action="skipped_short_text",
                reason=f"Only {len(clean_text)} chars after cleaning.",
            )
            continue

        result = detect_language(clean_text, config.min_confidence)

        # Optionally adjudicate with Ollama.
        if config.use_ollama and result.language_name == "unknown":
            from subtagger.ollama_adjudicator import adjudicate_language
            ollama_result = adjudicate_language(
                clean_text, config.ollama_url, config.ollama_model
            )
            if ollama_result and ollama_result.language_name != "unknown":
                result = ollama_result

        if result.language_name == "unknown":
            logger.info(
                "Could not determine language for stream %d of %s.",
                stream.index,
                path.name,
            )
            audit.log_action(
                file_path=str(path),
                stream_index=stream.index,
                original_lang=stream.language,
                detected_lang="unknown",
                confidence=result.confidence,
                method=result.method,
                action="skipped_unknown",
                reason="Detection inconclusive.",
            )
            continue

        if config.report_only:
            print(
                f"  [REPORT] {path.name} stream {stream.index}: "
                f"{result.language_name} ({result.iso_639_2}) "
                f"confidence={result.confidence:.0%} via {result.method}"
            )
            audit.log_action(
                file_path=str(path),
                stream_index=stream.index,
                original_lang=stream.language,
                detected_lang=result.iso_639_2,
                confidence=result.confidence,
                method=result.method,
                action="reported",
                reason="report-only mode",
            )
            continue

        success = write_language_tag(
            path,
            stream.index,
            result.iso_639_2,
            config.dry_run,
            lang_iso_639_1=result.iso_639_1,
        )

        action = "tagged" if (success and not config.dry_run) else (
            "dry_run" if config.dry_run else "error"
        )
        audit.log_action(
            file_path=str(path),
            stream_index=stream.index,
            original_lang=stream.language,
            detected_lang=result.iso_639_2,
            confidence=result.confidence,
            method=result.method,
            action=action,
        )

        if success:
            tagged += 1

    return tagged


def _process_external_subtitle(path: Path, config, audit: AuditLog) -> int:
    """Detect the language of an external subtitle file and rename it."""
    raw_text = read_external_subtitle(path)
    if not raw_text:
        audit.log_action(
            file_path=str(path),
            action="error",
            reason="Could not read external subtitle.",
        )
        return 0

    clean_text = clean_subtitle_text(raw_text)

    if len(clean_text) < config.min_text_length:
        audit.log_action(
            file_path=str(path),
            action="skipped_short_text",
            reason=f"Only {len(clean_text)} chars after cleaning.",
        )
        return 0

    result = detect_language(clean_text, config.min_confidence)

    if config.use_ollama and result.language_name == "unknown":
        from subtagger.ollama_adjudicator import adjudicate_language
        ollama_result = adjudicate_language(clean_text, config.ollama_url, config.ollama_model)
        if ollama_result and ollama_result.language_name != "unknown":
            result = ollama_result

    if result.language_name == "unknown":
        audit.log_action(
            file_path=str(path),
            detected_lang="unknown",
            confidence=result.confidence,
            method=result.method,
            action="skipped_unknown",
            reason="Detection inconclusive.",
        )
        return 0

    if config.report_only:
        print(
            f"  [REPORT] {path.name}: "
            f"{result.language_name} ({result.iso_639_2}) "
            f"confidence={result.confidence:.0%} via {result.method}"
        )
        audit.log_action(
            file_path=str(path),
            detected_lang=result.iso_639_2,
            confidence=result.confidence,
            method=result.method,
            action="reported",
            reason="report-only mode",
        )
        return 0

    success = write_language_tag(
        path,
        stream_index=-1,
        lang_iso_639_2=result.iso_639_2,
        dry_run=config.dry_run,
        lang_iso_639_1=result.iso_639_1,
    )

    action = "tagged" if (success and not config.dry_run) else (
        "dry_run" if config.dry_run else "error"
    )
    audit.log_action(
        file_path=str(path),
        detected_lang=result.iso_639_2,
        confidence=result.confidence,
        method=result.method,
        action=action,
    )
    return 1 if success else 0


def _run_once(scan_targets: list[str], config, audit: AuditLog) -> None:
    """Execute one full scan-and-tag pass."""
    all_files = scan_paths(scan_targets, config)
    media_files, subtitle_files = split_media_and_subtitles(all_files)

    logger.info(
        "Found %d media file(s) and %d external subtitle file(s).",
        len(media_files),
        len(subtitle_files),
    )

    total_tagged = 0

    for mf in media_files:
        try:
            total_tagged += _process_media_file(mf, config, audit)
        except Exception as exc:  # noqa: BLE001
            logger.error("Unexpected error processing %s: %s", mf, exc)
            audit.log_action(file_path=str(mf), action="error", reason=str(exc))

    for sf in subtitle_files:
        try:
            total_tagged += _process_external_subtitle(sf, config, audit)
        except Exception as exc:  # noqa: BLE001
            logger.error("Unexpected error processing %s: %s", sf, exc)
            audit.log_action(file_path=str(sf), action="error", reason=str(exc))

    logger.info("Pass complete — %d stream(s)/file(s) tagged.", total_tagged)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    """Main entry point for the ``subtagger`` CLI.

    Args:
        argv: Argument list (defaults to ``sys.argv[1:]``).

    Returns:
        Exit code (0 = success, 1 = error).
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Build config overrides from CLI flags.
    overrides: dict = {}
    if args.dry_run:
        overrides["dry_run"] = True
    if args.report_only:
        overrides["report_only"] = True
    if args.min_confidence is not None:
        overrides["min_confidence"] = args.min_confidence
    if args.watch_mode:
        overrides["watch_mode"] = True
    if args.log_level is not None:
        overrides["log_level"] = args.log_level
    if args.no_whisper:
        overrides["use_whisper_fallback"] = False
    if args.no_ollama:
        overrides["use_ollama"] = False

    config = load_config(path=args.config, overrides=overrides)
    setup_logging(config.log_level)

    # Merge CLI paths into scan_paths.
    scan_targets: list[str] = list(config.scan_paths)
    if args.paths:
        scan_targets = list(args.paths) + scan_targets

    if not scan_targets:
        parser.print_help()
        print("\nError: no scan paths specified (use positional PATH args or scan_paths in config).")
        return 1

    audit = AuditLog(config.audit_log_path)

    try:
        if config.watch_mode:
            logger.info(
                "Watch mode enabled — scanning every %d seconds.", config.watch_interval
            )
            while True:
                _run_once(scan_targets, config, audit)
                stats = audit.get_summary()
                print_summary(stats)
                logger.info("Sleeping %d seconds until next scan …", config.watch_interval)
                time.sleep(config.watch_interval)
        else:
            _run_once(scan_targets, config, audit)
            stats = audit.get_summary()
            print_summary(stats)
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
    finally:
        audit.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
