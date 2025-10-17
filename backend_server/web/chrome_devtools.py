"""Client-side helpers for interacting with a chrome-devtools-mcp server."""

from __future__ import annotations

import base64
import json
import logging
import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

logger = logging.getLogger(__name__)


class ChromeDevToolsMCPError(RuntimeError):
    """Raised when the chrome-devtools-mcp integration cannot satisfy a request."""


def _resolve_cli_command(override: str | None) -> List[str]:
    """Return the command list used to invoke the ``mcp_use`` CLI."""

    if override:
        parts = shlex.split(override)
        if not parts:
            raise ChromeDevToolsMCPError("CHROME_MCP_CLI override produced an empty command")
        return parts

    candidates = ("mcp", "mcp_use", "mcp-use")
    for candidate in candidates:
        path = shutil.which(candidate)
        if not path:
            continue
        if candidate == "mcp":
            return [path, "use"]
        return [path]

    raise ChromeDevToolsMCPError(
        "Unable to locate the 'mcp_use' CLI. Install the 'mcp' package or provide "
        "the executable path via the CHROME_MCP_CLI environment variable."
    )


@dataclass
class _SwitchToHelper:
    """Mimic the subset of Selenium's ``switch_to`` API used by the runner."""

    driver: "ChromeDevToolsMCPDriver"

    def window(self, _handle: str) -> None:
        logger.debug("chrome-devtools-mcp driver ignoring switch_to.window request")


class ChromeDevToolsMCPDriver:
    """Minimal driver shim that proxies actions through ``chrome-devtools-mcp``."""

    def __init__(
        self,
        server_url: str | None = None,
        *,
        cli: str | None = None,
        tool_name: str | None = None,
        action_tool: str | None = None,
        page_source_tool: str | None = None,
        screenshot_tool: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.server_url = server_url or os.getenv("CHROME_MCP_SERVER", "http://10.160.13.110:8882/sse")
        if not self.server_url:
            raise ChromeDevToolsMCPError("A chrome-devtools-mcp server URL is required")

        self.tool_name = tool_name or os.getenv("CHROME_MCP_TOOL", "chrome-devtools-mcp")
        if not self.tool_name:
            raise ChromeDevToolsMCPError("A chrome-devtools-mcp tool name is required")

        cli_override = cli or os.getenv("CHROME_MCP_CLI")
        self._command = _resolve_cli_command(cli_override)
        self._action_tool = action_tool or os.getenv("CHROME_MCP_ACTION_TOOL", "perform_action")
        self._page_source_tool = page_source_tool or os.getenv("CHROME_MCP_PAGE_SOURCE_TOOL", "page_source")
        self._screenshot_tool = screenshot_tool or os.getenv("CHROME_MCP_SCREENSHOT_TOOL", "screenshot")
        timeout_value = timeout if timeout is not None else float(os.getenv("CHROME_MCP_TIMEOUT", "60"))
        self._timeout = max(1.0, timeout_value)

        # Selenium compatibility shims used by helper utilities in ``runner.py``.
        self.capabilities: Dict[str, Any] = {"browserName": "chrome"}
        self.switch_to = _SwitchToHelper(self)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _build_command(self, operation: str, payload: Dict[str, Any] | None = None) -> List[str]:
        command = list(self._command)
        command.extend(["--server", self.server_url, "--tool", self.tool_name, "--name", operation])
        if payload:
            command.extend(["--input", json.dumps(payload)])
        return command

    def _call_tool(self, operation: str, payload: Dict[str, Any] | None = None) -> Any:
        command = self._build_command(operation, payload)
        logger.debug("chrome-devtools-mcp invoking: %s", command)
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
        except FileNotFoundError as exc:  # pragma: no cover - handled by resolver normally
            raise ChromeDevToolsMCPError(f"Failed to execute '{command[0]}': {exc}") from exc
        except subprocess.TimeoutExpired as exc:  # pragma: no cover - depends on runtime
            raise ChromeDevToolsMCPError(
                f"chrome-devtools-mcp command timed out after {self._timeout:.0f}s"
            ) from exc

        if result.returncode != 0:
            stderr = result.stderr.strip()
            stdout = result.stdout.strip()
            message = stderr or stdout or f"exit status {result.returncode}"
            raise ChromeDevToolsMCPError(f"chrome-devtools-mcp command failed: {message}")

        stdout = result.stdout.strip()
        if not stdout:
            return {}

        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            logger.debug("Received non-JSON payload from chrome-devtools-mcp: %s", stdout)
            return stdout

    # ------------------------------------------------------------------
    # Selenium compatibility surface
    # ------------------------------------------------------------------
    def implicitly_wait(self, _seconds: float) -> None:
        logger.debug("chrome-devtools-mcp driver ignoring implicitly_wait call")

    @property
    def window_handles(self) -> List[str]:  # pragma: no cover - simple shim
        return []

    @property
    def page_source(self) -> str:
        return self.get_page_source()

    # ------------------------------------------------------------------
    # High level helpers used by ``runner.py``
    # ------------------------------------------------------------------
    def perform_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(action, dict):
            raise ChromeDevToolsMCPError("Action payload must be a dictionary")

        action_name = str(action.get("action", "")).strip().lower()
        if action_name in {"finish", "error"}:
            return {"status": "noop"}

        response = self._call_tool(self._action_tool, {"action": action})
        if isinstance(response, dict):
            return response
        return {"status": str(response)}

    def get_page_source(self) -> str:
        response = self._call_tool(self._page_source_tool)
        if isinstance(response, dict):
            for key in ("html", "markup", "content", "page_source"):
                value = response.get(key)
                if isinstance(value, str) and value.strip():
                    return value
        if isinstance(response, str) and response.strip():
            return response
        raise ChromeDevToolsMCPError("chrome-devtools-mcp did not return page source content")

    def get_screenshot_png(self) -> bytes:
        response = self._call_tool(self._screenshot_tool)
        candidates: Iterable[Any]
        if isinstance(response, dict):
            candidates = response.values()
        else:
            candidates = (response,)

        for candidate in candidates:
            if isinstance(candidate, (bytes, bytearray)):
                return bytes(candidate)
            if isinstance(candidate, str):
                try:
                    return base64.b64decode(candidate)
                except Exception:  # pragma: no cover - depends on runtime payloads
                    continue
        raise ChromeDevToolsMCPError("chrome-devtools-mcp did not include screenshot data")

    def save_screenshot(self, path: str) -> None:
        data = self.get_screenshot_png()
        with open(path, "wb") as handle:
            handle.write(data)

    def get(self, url: str) -> Dict[str, Any]:
        if not isinstance(url, str) or not url.strip():
            raise ChromeDevToolsMCPError("A URL string is required for navigation")
        response = self._call_tool(self._action_tool, {"action": {"action": "navigate", "url": url}})
        if isinstance(response, dict):
            return response
        return {"status": str(response)}

    def quit(self) -> None:  # pragma: no cover - shutdown best effort
        try:
            self._call_tool("close")
        except ChromeDevToolsMCPError as exc:
            logger.debug("Ignoring chrome-devtools-mcp quit error: %s", exc)

