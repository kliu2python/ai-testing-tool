"""NiceGUI frontend for interacting with the AI Testing Tool API."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx
from nicegui import events, ui

API_BASE_DEFAULT = "http://localhost:8090"


@dataclass
class APIResult:
    """Represents the outcome of an API request."""

    ok: bool
    status: int
    data: Optional[Any]
    error: Optional[str]


class APIClient:
    """Small helper around httpx to interact with the backend API."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    async def request(
        self,
        method: str,
        endpoint: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> APIResult:
        """Execute an HTTP request against the configured API."""

        async with httpx.AsyncClient(base_url=self.base_url) as client:
            try:
                response = await client.request(method, endpoint, json=payload)
            except httpx.HTTPError as exc:
                return APIResult(False, 0, None, str(exc))

        if response.headers.get("content-type", "").startswith(
            "application/json"
        ):
            data: Optional[Any] = response.json()
        elif response.text:
            data = {"message": response.text}
        else:
            data = None

        error = None
        if not response.is_success:
            error = (
                data.get("detail") if isinstance(data, dict) else response.text
            )

        return APIResult(response.is_success, response.status_code, data, error)

    def update_base_url(self, base_url: str) -> None:
        """Update the API host used for subsequent requests."""

        self.base_url = base_url.rstrip("/")


api_client = APIClient(API_BASE_DEFAULT)


def _format_payload(payload: Optional[Any]) -> str:
    """Serialize payloads for display in the UI."""

    if payload is None:
        return ""
    return json.dumps(payload, indent=2)


with ui.header().classes("items-center justify-between"):
    ui.label("AI Testing Tool Frontend").classes("text-2xl font-semibold")
    ui.label("Interact with the FastAPI backend using NiceGUI")

with ui.card():
    ui.label("API Configuration").classes("text-xl font-semibold mb-2")
    base_url_input = (
        ui.input(
            "API Base URL",
            value=API_BASE_DEFAULT,
            on_change=lambda e: api_client.update_base_url(e.value),
        )
        .props("filled")
        .classes("w-full")
    )

    health_output = ui.label("Health status: unknown")

    async def check_health() -> None:
        result = await api_client.request("GET", "/")
        if result.ok and result.data:
            message = result.data.get("status", "unknown")
            ui.notify(f"API healthy: {message}", type="positive")
            health_output.text = f"Health status: {message}"
        else:
            ui.notify(
                f"Health check failed: {result.error or result.status}",
                type="negative",
            )
            health_output.text = "Health status: unavailable"

    ui.button("Check Health", on_click=check_health)


with ui.card():
    ui.label("Run Automation Tasks").classes("text-xl font-semibold mb-2")
    prompt_input = ui.textarea("Prompt").props("filled auto-grow")
    prompt_input.value = "Describe the tasks for the automation agent."

    tasks_input = ui.textarea("Tasks (JSON list)").props("filled auto-grow")
    tasks_input.value = json.dumps(
        [
            {
                "description": "Open the application and perform checks.",
                "actions": ["launch", "validate"],
            }
        ],
        indent=2,
    )

    server_input = ui.input("Automation Server", value="http://localhost:4723")
    platform_input = ui.select(
        ["android", "ios", "web"],
        value="android",
        label="Platform",
    )
    reports_input = ui.input("Reports Folder", value="./reports")
    debug_toggle = ui.switch("Enable Debug Mode")

    run_output = ui.code("", language="json").classes("w-full")

    async def submit_run() -> None:
        try:
            tasks_payload = json.loads(tasks_input.value or "[]")
        except json.JSONDecodeError as exc:
            ui.notify(f"Invalid tasks JSON: {exc}", type="negative")
            return

        payload = {
            "prompt": prompt_input.value,
            "tasks": tasks_payload,
            "server": server_input.value,
            "platform": platform_input.value,
            "reports_folder": reports_input.value,
            "debug": bool(debug_toggle.value),
        }

        result = await api_client.request("POST", "/run", payload)
        if result.ok:
            ui.notify("Task queued successfully", type="positive")
        else:
            ui.notify(
                f"Failed to queue task: {result.error or result.status}",
                type="negative",
            )
        run_output.set_content(_format_payload(result.data))

    ui.button("Submit Run Request", on_click=submit_run)


with ui.card():
    ui.label("Task Management").classes("text-xl font-semibold mb-2")
    tasks_output = ui.code("", language="json").classes("w-full")

    async def refresh_tasks() -> None:
        result = await api_client.request("GET", "/tasks")
        if result.ok:
            ui.notify("Fetched tasks", type="positive")
        else:
            ui.notify(
                f"Failed to fetch tasks: {result.error or result.status}",
                type="negative",
            )
        tasks_output.set_content(_format_payload(result.data))

    ui.button("Refresh Tasks", on_click=refresh_tasks)

    status_input = ui.input("Task ID for Status Lookup").props("filled")
    status_output = ui.code("", language="json").classes("w-full")

    async def fetch_status(_: Optional[events.ClickEvent] = None) -> None:
        task_id = status_input.value.strip()
        if not task_id:
            ui.notify("Enter a task ID", type="warning")
            return
        endpoint = f"/tasks/{task_id}"
        result = await api_client.request("GET", endpoint)
        if result.ok:
            ui.notify("Status retrieved", type="positive")
        else:
            ui.notify(
                f"Failed to fetch status: {result.error or result.status}",
                type="negative",
            )
        status_output.set_content(_format_payload(result.data))

    ui.button("Get Task Status", on_click=fetch_status)

    result_output = ui.code("", language="json").classes("w-full")

    async def fetch_result() -> None:
        task_id = status_input.value.strip()
        if not task_id:
            ui.notify("Enter a task ID", type="warning")
            return
        endpoint = f"/tasks/{task_id}/result"
        result = await api_client.request("GET", endpoint)
        if result.ok:
            ui.notify("Result retrieved", type="positive")
        else:
            ui.notify(
                f"Failed to fetch result: {result.error or result.status}",
                type="negative",
            )
        result_output.set_content(_format_payload(result.data))

    ui.button("Get Task Result", on_click=fetch_result)


ui.run(title="AI Testing Tool Frontend")
