"""Integration helpers for the ``chrome-devtools-mcp`` package.

The upstream project (https://github.com/ChromeDevTools/chrome-devtools-mcp)
exposes a Model Context Protocol (MCP) server that allows agents to control a
Chrome browser via the DevTools protocol.  This module makes it simple to load
and run that server from within the ai-testing-tool codebase without hard coding
knowledge of the upstream package's internal structure.

The helpers perform a best-effort discovery of the :class:`~mcp.server.fastmcp.FastMCP`
instance or factory provided by ``chrome-devtools-mcp``.  This keeps our
integration resilient to minor upstream refactors while still providing a clear
error message when the package is missing or exports an unexpected interface.
"""

from __future__ import annotations

import importlib
import inspect
from types import ModuleType
from typing import Any, Callable, Dict

try:  # pragma: no cover - imported dynamically in production environments
    from mcp.server.fastmcp import FastMCP
except ModuleNotFoundError as exc:  # pragma: no cover - import guard
    raise ImportError(
        "The 'mcp' package is required to run the Chrome DevTools MCP server. "
        "Install it with 'pip install mcp'."
    ) from exc


class ChromeDevToolsIntegrationError(RuntimeError):
    """Base class for chrome-devtools-mcp integration related errors."""


def _load_module() -> ModuleType:
    """Import and return the ``chrome_devtools_mcp`` module."""

    try:
        return importlib.import_module("chrome_devtools_mcp")
    except ModuleNotFoundError as exc:
        raise ChromeDevToolsIntegrationError(
            "The 'chrome-devtools-mcp' package is not installed. "
            "Install it from https://github.com/ChromeDevTools/chrome-devtools-mcp "
            "to enable Chrome automation via MCP."
        ) from exc


def _is_fastmcp(candidate: Any) -> bool:
    """Return ``True`` when *candidate* looks like a :class:`FastMCP` instance."""

    return isinstance(candidate, FastMCP)


def _call_factory(factory: Callable[..., Any], config: Dict[str, Any]) -> Any:
    """Invoke *factory* using only the keyword parameters it accepts."""

    try:
        signature = inspect.signature(factory)
    except (TypeError, ValueError):  # pragma: no cover - builtin/extension callables
        signature = None

    if signature is None:
        # Fallback to calling the factory without passing configuration if the
        # signature cannot be inspected (e.g. C extensions).
        return factory()

    supported_kwargs: Dict[str, Any] = {}
    for name, parameter in signature.parameters.items():
        if parameter.kind in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        ) and name in config:
            supported_kwargs[name] = config[name]

    try:
        return factory(**supported_kwargs)
    except TypeError:
        # Retry without keyword arguments in case the factory performs its own
        # validation and rejects partial kwargs.
        return factory()


def _discover_fastmcp(module: ModuleType, config: Dict[str, Any]) -> FastMCP:
    """Locate a :class:`FastMCP` instance or factory within *module*."""

    attribute_candidates = (
        "server",
        "app",
        "mcp",
        "fastmcp",
        "chrome_devtools_mcp",
        "CHROME_DEVTOOLS_MCP",
    )

    for attribute_name in attribute_candidates:
        candidate = getattr(module, attribute_name, None)
        if _is_fastmcp(candidate):
            return candidate

    factory_candidates = (
        "create_server",
        "create_app",
        "build_server",
        "make_server",
        "factory",
    )

    for factory_name in factory_candidates:
        factory = getattr(module, factory_name, None)
        if callable(factory):
            candidate = _call_factory(factory, config)
            if _is_fastmcp(candidate):
                return candidate

    raise ChromeDevToolsIntegrationError(
        "Unable to locate a FastMCP server inside the 'chrome-devtools-mcp' package. "
        "Ensure you are using a compatible version of the integration."
    )


def create_chrome_devtools_server(**config: Any) -> FastMCP:
    """Return the Chrome DevTools :class:`FastMCP` server instance.

    Parameters provided via ``**config`` are forwarded to the upstream factory
    when possible. Unsupported keys are ignored to remain forward compatible
    with upstream changes.
    """

    module = _load_module()
    return _discover_fastmcp(module, dict(config))


def run_chrome_devtools_server(**config: Any) -> None:
    """Execute the Chrome DevTools MCP server in the current process."""

    server = create_chrome_devtools_server(**config)
    server.run()
