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
import sys

from core.request_context import current_context


LOG_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)s [%(filename)s:%(lineno)d]"
    " | request_id=%(request_id)s job_id=%(job_id)s user_id=%(user_id)s | %(message)s"
)
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        context = current_context()
        record.request_id = context.request_id or "-"
        record.job_id = context.job_id or "-"
        record.user_id = context.user_id or "-"
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
