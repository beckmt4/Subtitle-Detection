"""Configuration management for SubTagger.

Loads configuration from a YAML file and overrides values with
environment variables or explicit keyword overrides.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Environment-variable prefix used for all config keys.
_ENV_PREFIX = "SUBTAGGER_"

# Mapping from env-var suffix → (config field name, type coercion callable)
_ENV_MAP: dict[str, tuple[str, Any]] = {
    "CONFIG": ("_config_path", str),
    "LOG_LEVEL": ("log_level", str),
    "DRY_RUN": ("dry_run", lambda v: v.lower() in ("1", "true", "yes")),
    "REPORT_ONLY": ("report_only", lambda v: v.lower() in ("1", "true", "yes")),
    "MIN_CONFIDENCE": ("min_confidence", float),
    "MIN_TEXT_LENGTH": ("min_text_length", int),
    "USE_WHISPER": ("use_whisper_fallback", lambda v: v.lower() in ("1", "true", "yes")),
    "USE_OLLAMA": ("use_ollama", lambda v: v.lower() in ("1", "true", "yes")),
    "OLLAMA_URL": ("ollama_url", str),
    "OLLAMA_MODEL": ("ollama_model", str),
    "WHISPER_MODEL": ("whisper_model", str),
    "AUDIT_LOG": ("audit_log_path", str),
    "WATCH_MODE": ("watch_mode", lambda v: v.lower() in ("1", "true", "yes")),
    "WATCH_INTERVAL": ("watch_interval", int),
}


@dataclass
class Config:
    """Top-level configuration dataclass for SubTagger."""

    scan_paths: list[str] = field(default_factory=list)
    include_extensions: list[str] = field(
        default_factory=lambda: [".mkv", ".mp4", ".srt", ".ass", ".ssa", ".vtt"]
    )
    exclude_patterns: list[str] = field(default_factory=list)
    dry_run: bool = False
    report_only: bool = False
    min_confidence: float = 0.85
    min_text_length: int = 50
    use_whisper_fallback: bool = False
    use_ollama: bool = False
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3"
    whisper_model: str = "base"
    audit_log_path: str = "subtagger_audit.db"
    log_level: str = "INFO"
    watch_mode: bool = False
    watch_interval: int = 3600


def _load_yaml(path: str) -> dict[str, Any]:
    """Read a YAML config file and return its contents as a dict."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
            return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        logger.debug("Config file not found: %s — using defaults.", path)
        return {}
    except yaml.YAMLError as exc:
        logger.warning("Failed to parse config file %s: %s", path, exc)
        return {}


def load_config(path: str | None = None, overrides: dict[str, Any] | None = None) -> Config:
    """Load configuration with layered precedence.

    Precedence (highest wins): explicit *overrides* dict > environment
    variables > YAML file > dataclass defaults.

    Args:
        path: Path to a YAML config file.  If *None*, ``config.yml`` in the
              current working directory is tried, then the path stored in the
              ``SUBTAGGER_CONFIG`` environment variable.
        overrides: Key/value pairs that unconditionally override all other
                   sources.  Keys must match :class:`Config` field names.

    Returns:
        A fully populated :class:`Config` instance.
    """
    if overrides is None:
        overrides = {}

    # Determine the YAML path to try.
    if path is None:
        path = os.environ.get(_ENV_PREFIX + "CONFIG", "config.yml")

    yaml_data = _load_yaml(path)

    # Start from defaults.
    cfg = Config()

    # Apply YAML values.
    for key, value in yaml_data.items():
        if hasattr(cfg, key):
            setattr(cfg, key, value)
        else:
            logger.debug("Unknown config key in YAML: %s", key)

    # Apply environment-variable overrides.
    for env_suffix, (field_name, coerce) in _ENV_MAP.items():
        env_key = _ENV_PREFIX + env_suffix
        raw = os.environ.get(env_key)
        if raw is not None and hasattr(cfg, field_name):
            try:
                setattr(cfg, field_name, coerce(raw))
                logger.debug("Config %s set from env %s=%s", field_name, env_key, raw)
            except (ValueError, TypeError) as exc:
                logger.warning("Could not coerce env %s=%r: %s", env_key, raw, exc)

    # Apply explicit overrides.
    for key, value in overrides.items():
        if hasattr(cfg, key):
            setattr(cfg, key, value)
        else:
            logger.debug("Unknown override key: %s", key)

    logger.debug("Effective config: %s", cfg)
    return cfg
