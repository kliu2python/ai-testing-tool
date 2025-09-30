"""Backend server package exposing automation orchestration utilities."""

from backend_server.logging_config import configure_logging

configure_logging()

__all__ = ["configure_logging"]
