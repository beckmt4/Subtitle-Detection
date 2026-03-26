"""Whisper-based audio transcription fallback for SubTagger.

When subtitle text cannot be extracted or is too short, this module uses
``faster-whisper`` to transcribe a brief audio sample and return the
transcript for language detection.
"""
from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Length (in seconds) of the audio sample extracted for detection.
_SAMPLE_DURATION_SECONDS = 60


def _extract_audio_sample(media_path: Path, duration: int) -> Path | None:
    """Extract a short audio clip from *media_path* using ffmpeg.

    The clip is written to the working directory as a temporary WAV file.

    Args:
        media_path: Source media file.
        duration: Number of seconds to extract starting from the beginning.

    Returns:
        Path to the temporary WAV file, or *None* on failure.
    """
    out_path = Path(f"._subtagger_audio_{os.getpid()}.wav")
    cmd = [
        "ffmpeg",
        "-y",
        "-v", "quiet",
        "-i", str(media_path),
        "-vn",
        "-t", str(duration),
        "-ar", "16000",
        "-ac", "1",
        str(out_path),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0 or not out_path.exists():
            logger.warning(
                "ffmpeg audio extraction failed (exit %d): %s",
                result.returncode,
                result.stderr[:200],
            )
            return None
        return out_path
    except FileNotFoundError:
        logger.error("ffmpeg not found — cannot extract audio for Whisper.")
        return None
    except subprocess.TimeoutExpired:
        logger.error("ffmpeg timed out extracting audio from %s", media_path)
        return None
    except OSError as exc:
        logger.error("OS error extracting audio from %s: %s", media_path, exc)
        return None


def transcribe_audio(path: Path, model_name: str = "base") -> str | None:
    """Transcribe the first ~60 seconds of *path* using Faster-Whisper.

    Args:
        path: Path to the media file (video or audio).
        model_name: Faster-Whisper model size identifier (e.g. ``"base"``,
                    ``"small"``, ``"medium"``).

    Returns:
        Transcribed text as a single string, or *None* when transcription
        fails or faster-whisper is not installed.
    """
    try:
        from faster_whisper import WhisperModel  # type: ignore[import]
    except ImportError:
        logger.warning(
            "faster-whisper is not installed; audio transcription unavailable."
        )
        return None

    audio_path = _extract_audio_sample(path, _SAMPLE_DURATION_SECONDS)
    if audio_path is None:
        return None

    try:
        logger.info("Loading Whisper model '%s' …", model_name)
        model = WhisperModel(model_name, device="cpu", compute_type="int8")

        logger.info("Transcribing audio sample from %s …", path.name)
        segments, _info = model.transcribe(
            str(audio_path),
            beam_size=5,
            language=None,  # auto-detect
        )

        transcript = " ".join(seg.text for seg in segments).strip()
        logger.debug("Whisper transcript (%d chars): %s…", len(transcript), transcript[:100])
        return transcript if transcript else None

    except Exception as exc:  # noqa: BLE001
        logger.error("Whisper transcription error for %s: %s", path, exc)
        return None

    finally:
        if audio_path.exists():
            try:
                audio_path.unlink()
            except OSError:
                pass
