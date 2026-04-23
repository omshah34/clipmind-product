"""File: logging_config.py
Purpose: Centralized logging configuration for the entire ClipMind backend.
         Sets up a consistent log format that includes the source filename
         and line number in every log message, making errors easy to trace.

Usage:
    Import and call setup_logging() once at application startup:
        from core.logging_config import setup_logging
        setup_logging()
"""

import logging
import os
import re
import sys

from core.request_context import current_context


LOG_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)s [%(filename)s:%(lineno)d]"
    " | request_id=%(request_id)s job_id=%(job_id)s user_id=%(user_id)s | %(message)s"
)
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Regex patterns for PII redaction (Gap 47)
_EMAIL_RE = re.compile(r"([a-zA-Z0-9_.+-])([a-zA-Z0-9_.+-]*)@([a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)")
_FILEPATH_RE = re.compile(r"(?:/home/|/Users/|C:\\\\Users\\\\)[^/\\\\\s]+")


def _redact_pii(text: str) -> str:
    """Mask emails and personal file paths in log messages."""
    # Mask email: keep first char + *** before @
    text = _EMAIL_RE.sub(lambda m: f"{m.group(1)}***@{m.group(3)}", text)
    # Mask personal file paths
    text = _FILEPATH_RE.sub("[REDACTED_PATH]", text)
    return text


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        context = current_context()
        record.request_id = context.request_id or "-"
        record.job_id = context.job_id or "-"
        record.user_id = context.user_id or "-"
        # Gap 47: Redact PII from the log message itself
        if isinstance(record.msg, str):
            record.msg = _redact_pii(record.msg)
        return True


def setup_logging(level: str | None = None) -> None:
    """Configure the root logger with a format that includes source file info.

    Args:
        level: Override log level (e.g. "DEBUG", "INFO"). If None, reads from
               the LOG_LEVEL env var, defaulting to "INFO".
    """
    resolved_level = level or os.getenv("LOG_LEVEL", "INFO")

    root = logging.getLogger()
    root.setLevel(resolved_level.upper())

    # Remove any existing handlers to avoid duplicate output
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    # Console handler (stdout) — captured by run.py's log_stream
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(resolved_level.upper())
    console.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT))
    console.addFilter(ContextFilter())
    root.addHandler(console)

    # Quieten noisy third-party loggers
    for noisy in ("httpx", "httpcore", "urllib3", "watchfiles", "multipart"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
