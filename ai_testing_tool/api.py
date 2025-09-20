"""FastAPI application exposing the AI testing tool as a service."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .runner import RunResult, run_tasks


class Platform(str, Enum):
    """Supported automation platforms."""

    android = "android"
    ios = "ios"
    web = "web"


class RunRequest(BaseModel):
    """Request payload for running automation tasks."""

    prompt: str = Field(..., description="System prompt guiding the agent.")
    tasks: List[Dict[str, Any]] = Field(
        ..., description="List of task definitions to execute."
    )
    server: str = Field(
        "http://localhost:4723",
        description="Automation server address.",
    )
    platform: Platform = Field(
        Platform.android,
        description="Platform against which to run the tasks.",
    )
    reports_folder: str = Field(
        "./reports",
        description="Destination folder for generated reports.",
    )
    debug: bool = Field(
        False,
        description="Enable interactive debug mode requiring manual input.",
    )


class RunResponse(BaseModel):
    """Response payload containing aggregated run results."""

    summary: List[Dict[str, Any]]
    summary_path: str


app = FastAPI(title="AI Testing Tool API", version="1.0.0")


@app.get("/", summary="Health check")
def read_root() -> Dict[str, str]:
    """Return a simple status response indicating the API is online."""

    return {"status": "ok"}


@app.post("/run", response_model=RunResponse, summary="Run automation tasks")
def run_automation(request: RunRequest) -> RunResponse:
    """Execute automation tasks using the provided configuration."""

    try:
        result: RunResult = run_tasks(
            request.prompt,
            request.tasks,
            request.server,
            request.platform.value,
            request.reports_folder,
            request.debug,
        )
    except Exception as exc:  # pragma: no cover - propagate failure details
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return RunResponse(summary=result.summary, summary_path=result.summary_path)
