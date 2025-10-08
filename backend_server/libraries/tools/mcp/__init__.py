"""Model Context Protocol (MCP) server integrations."""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "fortigate_mcp",
    "create_chrome_devtools_server",
    "run_chrome_devtools_server",
]

_fortigate_instance = None
_fortigate_error: BaseException | None = None


def _load_fortigate_mcp():
    """Return the FortiGate FastMCP server, caching the result."""

    global _fortigate_instance, _fortigate_error

    if _fortigate_instance is not None:
        return _fortigate_instance
    if _fortigate_error is not None:
        raise _fortigate_error

    try:
        module = import_module("backend_server.libraries.tools.mcp.fortigate_mcp")
    except Exception as exc:  # pragma: no cover - depends on optional deps
        _fortigate_error = exc
        raise
    else:
        _fortigate_instance = module.fortigate_mcp
        return _fortigate_instance


def __getattr__(name: str):  # pragma: no cover - exercised indirectly
    if name == "fortigate_mcp":
        try:
            return _load_fortigate_mcp()
        except ModuleNotFoundError as exc:
            raise ImportError(
                "The FortiGate MCP integration dependencies are missing. "
                "Install the optional FortiGate requirements to enable it."
            ) from exc
    raise AttributeError(name)


def __dir__():  # pragma: no cover - used by interactive shells
    return sorted(set(globals()) | {"fortigate_mcp"})


def _load_chrome_devtools_module():
    """Lazy import helper for the Chrome DevTools MCP integration."""

    return import_module("backend_server.libraries.tools.mcp.chrome_devtools_mcp")


def create_chrome_devtools_server(**config: Any):
    """Return the Chrome DevTools FastMCP server instance.

    The implementation lives in :mod:`chrome_devtools_mcp` but is imported lazily
    so that ``chrome-devtools-mcp`` remains an optional dependency.
    """

    module = _load_chrome_devtools_module()
    return module.create_chrome_devtools_server(**config)


def run_chrome_devtools_server(**config: Any) -> None:
    """Execute the Chrome DevTools MCP server in the current process."""

    module = _load_chrome_devtools_module()
    module.run_chrome_devtools_server(**config)
