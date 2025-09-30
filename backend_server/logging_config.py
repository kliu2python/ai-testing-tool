"""Centralised logging configuration for the backend server package."""

from __future__ import annotations

import logging
import os
from typing import Iterable

_LOGGING_FORMAT = (
    "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)


def _coerce_level(value: str) -> int:
    """Return a valid logging level for ``value``.

    Defaults to :data:`logging.INFO` when ``value`` is not recognised.
    """

    if not value:
        return logging.INFO
    if isinstance(value, str):
        numeric = getattr(logging, value.upper(), None)
        if isinstance(numeric, int):
            return numeric
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return logging.INFO
        return parsed
    if isinstance(value, int):
        return value
    return logging.INFO


def _build_handlers(log_file: str | None) -> Iterable[logging.Handler]:
    """Return the logging handlers to use for configuration."""

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(logging.Formatter(_LOGGING_FORMAT))
    handlers = [stream_handler]

    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(logging.Formatter(_LOGGING_FORMAT))
        handlers.append(file_handler)

    return handlers


_configured = False


def configure_logging(force: bool = False) -> None:
    """Initialise logging for the backend package.

    The configuration honours the following environment variables:

    ``BACKEND_LOG_LEVEL``
        Specifies the root logging level (defaults to ``INFO``).
    ``BACKEND_LOG_FILE``
        Optional path to a file where logs should be written in addition to
        standard output.
    """

    global _configured
    if _configured and not force:
        return

    level = _coerce_level(os.getenv("BACKEND_LOG_LEVEL", "INFO"))
    log_file = os.getenv("BACKEND_LOG_FILE")

    handlers = list(_build_handlers(log_file))
    root_logger = logging.getLogger()

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    root_logger.setLevel(level)
    for handler in handlers:
        root_logger.addHandler(handler)

    _configured = True
