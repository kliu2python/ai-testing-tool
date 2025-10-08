"""Model Context Protocol server for FortiGate user management.

This module exposes a :class:`FastMCP` server that provides a curated set of
tools wrapping :mod:`libraries.cli.fortigate_library`.  The tools are centred
around common user-management workflows (create, delete, group membership,
etc.) so that an MCP compatible client can safely orchestrate user
modifications on a FortiGate appliance.

Environment variables
---------------------
The connection credentials can either be provided on every tool invocation or
populated via the following environment variables:

``FORTIGATE_HOST``
    Default FortiGate hostname or IP address.
``FORTIGATE_USERNAME``
    Default username used for SSH connections.
``FORTIGATE_PASSWORD``
    Default password used for SSH connections.
``FORTIGATE_DNS``
    Optional DNS server that should be configured before synchronisation.
``FORTIGATE_ALTERNATE_HOST``
    Optional alternate source IP used by ``FortigateBase.ping``.
``FORTIGATE_EMAIL``
    Optional email address used when creating users.
``FORTIGATE_TIMEOUT``
    Optional SSH command timeout expressed in seconds.

The server keeps the implementation dependency free except for the ``mcp``
package, allowing it to run both as a standalone binary (``python -m
tools.mcp.fortigate_mcp``) or to be imported and executed by tests.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional

try:
    from mcp.server.fastmcp import FastMCP
except ModuleNotFoundError as exc:  # pragma: no cover - import guard
    raise ImportError(
        "The 'mcp' package is required to use the FortiGate MCP server. "
        "Install it with 'pip install mcp'."
    ) from exc

from backend_server.libraries.cli.fortigate_library import FortigateBase
from backend_server.libraries.cli.users.fortigate_user import FortigateUser


@dataclass
class FortigateConnectionSettings:
    """Holds connection details used to instantiate :class:`FortigateBase`."""

    host: str
    username: str
    password: str
    dns: Optional[str] = None
    alternate_ip: Optional[str] = None
    email: Optional[str] = None
    timeout: int = 30
    display: bool = False

    @classmethod
    def from_env(cls) -> "FortigateConnectionSettings":
        """Create settings using environment variable fallbacks."""

        env_timeout = os.getenv("FORTIGATE_TIMEOUT")
        timeout = int(env_timeout) if env_timeout else 30

        host = os.getenv("FORTIGATE_HOST")
        username = os.getenv("FORTIGATE_USERNAME")
        password = os.getenv("FORTIGATE_PASSWORD")

        if not all([host, username, password]):
            raise ValueError(
                "FortiGate connection details must be provided via tool "
                "arguments or FORTIGATE_HOST, FORTIGATE_USERNAME and "
                "FORTIGATE_PASSWORD environment variables."
            )

        return cls(
            host=host,
            username=username,
            password=password,
            dns=os.getenv("FORTIGATE_DNS"),
            alternate_ip=os.getenv("FORTIGATE_ALTERNATE_HOST"),
            email=os.getenv("FORTIGATE_EMAIL"),
            timeout=timeout,
        )

    def apply_overrides(
        self,
        host: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        dns: Optional[str] = None,
        alternate_ip: Optional[str] = None,
        email: Optional[str] = None,
        timeout: Optional[int] = None,
        display: Optional[bool] = None,
    ) -> "FortigateConnectionSettings":
        """Return a copy of the settings with user supplied overrides."""

        return FortigateConnectionSettings(
            host=host or self.host,
            username=username or self.username,
            password=password or self.password,
            dns=dns if dns is not None else self.dns,
            alternate_ip=alternate_ip if alternate_ip is not None else self.alternate_ip,
            email=email if email is not None else self.email,
            timeout=timeout if timeout is not None else self.timeout,
            display=display if display is not None else self.display,
        )


def _resolve_settings(
    host: Optional[str],
    username: Optional[str],
    password: Optional[str],
    dns: Optional[str],
    alternate_ip: Optional[str],
    email: Optional[str],
    timeout: Optional[int],
    display: Optional[bool],
) -> FortigateConnectionSettings:
    """Resolve the connection settings from arguments or environment."""

    if timeout is not None:
        timeout = int(timeout)

    if host and username and password:
        base_settings = FortigateConnectionSettings(
            host=host,
            username=username,
            password=password,
            dns=dns,
            alternate_ip=alternate_ip,
            email=email,
            timeout=timeout or 30,
            display=display if display is not None else False,
        )
    else:
        base_settings = FortigateConnectionSettings.from_env()
        base_settings = base_settings.apply_overrides(
            host=host,
            username=username,
            password=password,
            dns=dns,
            alternate_ip=alternate_ip,
            email=email,
            timeout=timeout,
            display=display,
        )
    return base_settings


@contextmanager
def fortigate_connection(settings: FortigateConnectionSettings) -> Iterator[FortigateBase]:
    """Context manager yielding a connected :class:`FortigateBase` instance."""

    client = FortigateBase(
        dns=settings.dns,
        email_un=settings.email,
        fortigate_ip=settings.host,
        fortigate_un=settings.username,
        fortigate_pw=settings.password,
        alternate_ip=settings.alternate_ip,
        timeout=settings.timeout,
        display=settings.display,
    )
    try:
        yield client
    finally:
        client.quit()


def _serialise_user_groups(groups: Dict[str, List[FortigateUser]]) -> Dict[str, List[str]]:
    """Transform a FortiGate user group mapping into primitive types."""

    return {group: [user.name for user in members] for group, members in groups.items()}


def _normalise_outputs(outputs: Any) -> List[str]:
    """Ensure command outputs are returned as a list of strings."""

    if outputs is None:
        return []
    if isinstance(outputs, str):
        return [outputs]
    return [str(output) for output in outputs]


fortigate_mcp = FastMCP("fortigate-mcp")


@fortigate_mcp.tool()
def create_user(
    name: str,
    is_admin: bool = False,
    password: Optional[str] = None,
    vpn_group: Optional[str] = None,
    two_factor: Optional[str] = "fortitoken-cloud",
    email: Optional[str] = None,
    session_email: Optional[str] = None,
    sms_phone: Optional[str] = None,
    fortitoken: Optional[str] = None,
    multi_vdom: bool = True,
    vdom_name: str = "root",
    host: Optional[str] = None,
    username: Optional[str] = None,
    ssh_password: Optional[str] = None,
    dns: Optional[str] = None,
    alternate_ip: Optional[str] = None,
    timeout: Optional[int] = None,
    display: Optional[bool] = None,
) -> Dict[str, Any]:
    """Create a FortiGate user.

    Parameters
    ----------
    name:
        The user identifier that should be created.
    is_admin:
        When ``True`` an admin profile is provisioned in the global scope.
    password:
        Password assigned to the new user.  When omitted the FortiGate default
        of ``1234`` is utilised.
    vpn_group:
        Optional VPN group to add the user to after creation.
    two_factor:
        Two factor method, defaults to ``fortitoken-cloud``.
    email:
        Email address used for the created user.  Defaults to
        ``FORTIGATE_EMAIL`` (or ``session_email``) when present.
    session_email:
        Optional override for the connection level email when ``email`` is not
        supplied.
    sms_phone:
        Optional SMS phone number for MFA delivery.
    fortitoken:
        Optional FortiToken identifier to assign to the user.
    multi_vdom / vdom_name:
        Control whether the commands run inside a VDOM context.
    host / username / ssh_password / dns / alternate_ip / timeout / display:
        Optional overrides for the connection configuration.
    """

    settings = _resolve_settings(
        host=host,
        username=username,
        password=ssh_password,
        dns=dns,
        alternate_ip=alternate_ip,
        email=session_email,
        timeout=timeout,
        display=display,
    )

    user_email = email or settings.email
    user = FortigateUser(name=name, is_admin=is_admin, vpn_group=vpn_group)

    with fortigate_connection(settings) as conn:
        created_name = conn.create_user(
            new_user=user,
            email=user_email,
            password=password or 1234,
            two_factor=two_factor,
            multi_vdom=multi_vdom,
            display=False,
            vdom_name=vdom_name,
            sms_phone=sms_phone,
            fortitoken=fortitoken,
        )

    return {"user": created_name, "vpn_group": vpn_group}


@fortigate_mcp.tool()
def delete_user(
    name: str,
    is_admin: bool = False,
    multi_vdom: bool = True,
    vdom_name: str = "root",
    host: Optional[str] = None,
    username: Optional[str] = None,
    ssh_password: Optional[str] = None,
    dns: Optional[str] = None,
    alternate_ip: Optional[str] = None,
    timeout: Optional[int] = None,
    display: Optional[bool] = None,
) -> Dict[str, Any]:
    """Delete a FortiGate user."""

    settings = _resolve_settings(
        host=host,
        username=username,
        password=ssh_password,
        dns=dns,
        alternate_ip=alternate_ip,
        email=None,
        timeout=timeout,
        display=display,
    )

    user = FortigateUser(name=name, is_admin=is_admin)

    with fortigate_connection(settings) as conn:
        outputs = conn.delete_user(
            user,
            multi_vdom=multi_vdom,
            vdom_name=vdom_name,
            display=False,
            timeout=settings.timeout,
        )

    return {"outputs": _normalise_outputs(outputs)}


@fortigate_mcp.tool()
def list_user_groups(
    multi_vdom: bool = True,
    vdom_name: str = "root",
    host: Optional[str] = None,
    username: Optional[str] = None,
    ssh_password: Optional[str] = None,
    dns: Optional[str] = None,
    alternate_ip: Optional[str] = None,
    timeout: Optional[int] = None,
    display: Optional[bool] = None,
) -> Dict[str, Any]:
    """Return the current FortiGate user group membership."""

    settings = _resolve_settings(
        host=host,
        username=username,
        password=ssh_password,
        dns=dns,
        alternate_ip=alternate_ip,
        email=None,
        timeout=timeout,
        display=display,
    )

    with fortigate_connection(settings) as conn:
        groups = conn.get_user_groups(multi_vdom=multi_vdom, vdom_name=vdom_name)

    return {"groups": _serialise_user_groups(groups)}


@fortigate_mcp.tool()
def update_vpn_membership(
    name: str,
    vpn_group: str,
    action: str = "add",
    multi_vdom: bool = True,
    vdom_name: str = "root",
    host: Optional[str] = None,
    username: Optional[str] = None,
    ssh_password: Optional[str] = None,
    dns: Optional[str] = None,
    alternate_ip: Optional[str] = None,
    timeout: Optional[int] = None,
    display: Optional[bool] = None,
) -> Dict[str, Any]:
    """Add or remove a user from a VPN group."""

    if action not in {"add", "remove"}:
        raise ValueError("action must be either 'add' or 'remove'")

    settings = _resolve_settings(
        host=host,
        username=username,
        password=ssh_password,
        dns=dns,
        alternate_ip=alternate_ip,
        email=None,
        timeout=timeout,
        display=display,
    )

    user = FortigateUser(name=name, vpn_group=vpn_group)

    with fortigate_connection(settings) as conn:
        outputs = conn.modify_users_in_vpn(
            user=user,
            multi_vdom=multi_vdom,
            vdom_name=vdom_name,
            delete=(action == "remove"),
        )

    return {"outputs": _normalise_outputs(outputs), "action": action, "vpn_group": vpn_group}


def main() -> None:
    """Launch the MCP server when executed as a script."""

    fortigate_mcp.run()


if __name__ == "__main__":
    main()
