tools/mcp/__init__.py
New
+9
-0

"""Model Context Protocol server bootstrap for FortiGate operations.

This package exposes helpers to launch the FortiGate focussed MCP server.
"""

from .fortigate_mcp import fortigate_mcp

__all__ = ["fortigate_mcp"]