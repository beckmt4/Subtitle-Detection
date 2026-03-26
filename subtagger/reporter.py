"""Audit logging and reporting for SubTagger.

Provides an SQLite-backed audit log and a human-readable summary printer,
plus a helper to configure the Python root logger.
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def setup_logging(level: str = "INFO") -> None:
    """Configure the root logger with a consistent format.

    Args:
        level: One of ``"DEBUG"``, ``"INFO"``, ``"WARNING"``, ``"ERROR"``.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    logging.getLogger("subtagger").setLevel(numeric_level)


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS audit_log (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp      TEXT    NOT NULL,
    file_path      TEXT    NOT NULL,
    stream_index   INTEGER NOT NULL DEFAULT -1,
    original_lang  TEXT,
    detected_lang  TEXT,
    confidence     REAL,
    method         TEXT,
    action         TEXT    NOT NULL,
    reason         TEXT
);
"""


class AuditLog:
    """SQLite-backed audit log for SubTagger actions.

    Records every decision (detection, tag write, skip, error) so that runs
    can be reviewed and audited later.
    """

    def __init__(self, db_path: str = "subtagger_audit.db") -> None:
        """Open (or create) the audit database.

        Args:
            db_path: Path to the SQLite database file.
        """
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._open()

    def _open(self) -> None:
        """Open the database connection and create the schema if needed."""
        try:
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._conn.execute(_CREATE_TABLE_SQL)
            self._conn.commit()
            logger.debug("Audit log opened: %s", self._db_path)
        except sqlite3.Error as exc:
            logger.error("Failed to open audit log at %s: %s", self._db_path, exc)
            self._conn = None

    def log_action(
        self,
        file_path: str,
        stream_index: int = -1,
        original_lang: str | None = None,
        detected_lang: str | None = None,
        confidence: float = 0.0,
        method: str = "",
        action: str = "",
        reason: str = "",
    ) -> None:
        """Insert one row into the audit log.

        Args:
            file_path: Absolute or relative path of the processed file.
            stream_index: Stream index inside the container (``-1`` for
                          external subtitle files).
            original_lang: Language tag that was present before processing.
            detected_lang: Language code determined by detection.
            confidence: Detection confidence in ``[0, 1]``.
            method: Detection method used (``"lingua"``, ``"langdetect"``,
                    ``"ollama"``, ``"whisper"``, etc.).
            action: Short description of what was done (e.g. ``"tagged"``,
                    ``"skipped"``, ``"error"``).
            reason: Free-form explanation.
        """
        if self._conn is None:
            logger.debug("Audit log unavailable; skipping log_action.")
            return

        ts = datetime.now(tz=timezone.utc).isoformat()
        try:
            self._conn.execute(
                """
                INSERT INTO audit_log
                    (timestamp, file_path, stream_index, original_lang,
                     detected_lang, confidence, method, action, reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (ts, file_path, stream_index, original_lang,
                 detected_lang, confidence, method, action, reason),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            logger.error("Failed to write audit log entry: %s", exc)

    def get_summary(self) -> dict[str, Any]:
        """Return aggregate statistics from the audit log.

        Returns:
            A dict with keys:
            * ``total`` — total rows in the log.
            * ``tagged`` — rows where action == ``"tagged"``.
            * ``skipped`` — rows where action starts with ``"skipped"``.
            * ``errors`` — rows where action == ``"error"``.
            * ``by_language`` — ``{language_code: count}`` for tagged rows.
            * ``by_method`` — ``{method: count}`` for tagged rows.
        """
        if self._conn is None:
            return {"total": 0, "tagged": 0, "skipped": 0, "errors": 0,
                    "by_language": {}, "by_method": {}}

        try:
            cur = self._conn.cursor()

            cur.execute("SELECT COUNT(*) FROM audit_log")
            total: int = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'tagged'")
            tagged: int = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM audit_log WHERE action LIKE 'skipped%'")
            skipped: int = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'error'")
            errors: int = cur.fetchone()[0]

            cur.execute(
                "SELECT detected_lang, COUNT(*) FROM audit_log "
                "WHERE action = 'tagged' GROUP BY detected_lang"
            )
            by_language: dict[str, int] = {row[0]: row[1] for row in cur.fetchall() if row[0]}

            cur.execute(
                "SELECT method, COUNT(*) FROM audit_log "
                "WHERE action = 'tagged' GROUP BY method"
            )
            by_method: dict[str, int] = {row[0]: row[1] for row in cur.fetchall() if row[0]}

            return {
                "total": total,
                "tagged": tagged,
                "skipped": skipped,
                "errors": errors,
                "by_language": by_language,
                "by_method": by_method,
            }
        except sqlite3.Error as exc:
            logger.error("Failed to read audit log summary: %s", exc)
            return {"total": 0, "tagged": 0, "skipped": 0, "errors": 0,
                    "by_language": {}, "by_method": {}}

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __del__(self) -> None:
        self.close()


# ---------------------------------------------------------------------------
# Summary printer
# ---------------------------------------------------------------------------

def print_summary(stats: dict[str, Any]) -> None:
    """Print a human-readable run summary to stdout.

    Args:
        stats: Dictionary returned by :meth:`AuditLog.get_summary`.
    """
    print("\n" + "=" * 60)
    print("  SubTagger — Run Summary")
    print("=" * 60)
    print(f"  Total processed : {stats.get('total', 0)}")
    print(f"  Tagged          : {stats.get('tagged', 0)}")
    print(f"  Skipped         : {stats.get('skipped', 0)}")
    print(f"  Errors          : {stats.get('errors', 0)}")

    by_lang = stats.get("by_language", {})
    if by_lang:
        print("\n  Tags written by language:")
        for lang, count in sorted(by_lang.items(), key=lambda x: -x[1]):
            print(f"    {lang:<10} {count}")

    by_method = stats.get("by_method", {})
    if by_method:
        print("\n  Detection method breakdown:")
        for method, count in sorted(by_method.items(), key=lambda x: -x[1]):
            print(f"    {method:<16} {count}")

    print("=" * 60 + "\n")
