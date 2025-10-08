"""Tests for the chrome-devtools-mcp integration helpers."""

from __future__ import annotations

import importlib
import sys
import types
from typing import Dict

import pytest

MODULE_UNDER_TEST = "backend_server.libraries.tools.mcp.chrome_devtools_mcp"


@pytest.fixture(autouse=True)
def _reset_module_cache():
    """Ensure the module under test is reloaded between tests."""

    if MODULE_UNDER_TEST in sys.modules:
        del sys.modules[MODULE_UNDER_TEST]
    yield
    if MODULE_UNDER_TEST in sys.modules:
        del sys.modules[MODULE_UNDER_TEST]


@pytest.fixture(autouse=True)
def _install_fastmcp_stub(monkeypatch):
    """Provide a minimal stub for :mod:`mcp.server.fastmcp`."""

    fastmcp_module = types.ModuleType("mcp.server.fastmcp")

    class DummyFastMCP:  # pragma: no cover - simple stub
        def __init__(self, name: str = "stub") -> None:
            self.name = name
            self.run_called_with: Dict[str, object] | None = None

        def run(self, **kwargs):  # pragma: no cover - unused in tests
            self.run_called_with = kwargs

    fastmcp_module.FastMCP = DummyFastMCP

    server_package = types.ModuleType("mcp.server")
    server_package.fastmcp = fastmcp_module

    mcp_package = types.ModuleType("mcp")
    mcp_package.server = server_package

    sys.modules['mcp'] = mcp_package
    sys.modules['mcp.server'] = server_package
    sys.modules['mcp.server.fastmcp'] = fastmcp_module

    yield DummyFastMCP

    for module_name in ["mcp.server.fastmcp", "mcp.server", "mcp"]:
        sys.modules.pop(module_name, None)


def _install_chrome_module(monkeypatch, dummy_fastmcp, **attributes):
    module = types.ModuleType("chrome_devtools_mcp")
    for key, value in attributes.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, "chrome_devtools_mcp", module)
    return module


def test_returns_existing_server(monkeypatch, _install_fastmcp_stub):
    dummy_fastmcp = _install_fastmcp_stub
    _install_chrome_module(monkeypatch, dummy_fastmcp, server=dummy_fastmcp("chrome"))

    module = importlib.import_module(MODULE_UNDER_TEST)
    server = module.create_chrome_devtools_server()

    assert isinstance(server, dummy_fastmcp)
    assert server.name == "chrome"


def test_invokes_factory_with_supported_kwargs(monkeypatch, _install_fastmcp_stub):
    dummy_fastmcp = _install_fastmcp_stub

    captured_kwargs = {}

    def factory(*, user_data_dir: str, headless: bool = True):
        captured_kwargs.update({"user_data_dir": user_data_dir, "headless": headless})
        return dummy_fastmcp("factory")

    _install_chrome_module(monkeypatch, dummy_fastmcp, create_server=factory)

    module = importlib.import_module(MODULE_UNDER_TEST)
    server = module.create_chrome_devtools_server(
        user_data_dir="/tmp/profile",
        headless=False,
        unsupported="ignored",
    )

    assert isinstance(server, dummy_fastmcp)
    assert server.name == "factory"
    assert captured_kwargs == {"user_data_dir": "/tmp/profile", "headless": False}


def test_missing_package_raises_helpful_error(monkeypatch):
    sys.modules.pop("chrome_devtools_mcp", None)
    module = importlib.import_module(MODULE_UNDER_TEST)

    with pytest.raises(module.ChromeDevToolsIntegrationError) as exc:
        module.create_chrome_devtools_server()

    assert "chrome-devtools-mcp" in str(exc.value)
