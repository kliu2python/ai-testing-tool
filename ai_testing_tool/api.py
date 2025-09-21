"""FastAPI application exposing the AI testing tool as a service."""
from __future__ import annotations

import os
from enum import Enum
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from runner import RunResult, run_tasks


# -----------------------------
# Models
# -----------------------------
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
        description="Automation server address (e.g., Appium/Selenium).",
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


# -----------------------------
# App
# -----------------------------
app = FastAPI(
    title="AI Testing Tool API",
    version="1.0.0",
    description="Run cross-platform automation tasks (Android/iOS/Web) via an AI agent.",
)

# CORS (adjust origins as needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ALLOW_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _ensure_reports_folder() -> None:
    # Create the default reports folder up front so writes won't fail.
    default_reports = "./reports"
    try:
        os.makedirs(default_reports, exist_ok=True)
    except Exception as exc:  # pragma: no cover
        # Not fatal; individual runs also try to create their own paths.
        print(f"[WARN] Failed to create default reports folder '{default_reports}': {exc}")


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


# -----------------------------
# Entrypoint
# -----------------------------
if __name__ == "__main__":
    # Environment-configurable server settings
    host = os.getenv("APP_HOST", "0.0.0.0")
    port = int(os.getenv("APP_PORT", "8090"))
    reload_opt = os.getenv("APP_RELOAD", "true").lower() in {"1", "true", "yes"}

    import uvicorn

    uvicorn.run(
        "api:app",  # if your file name is app.py; otherwise use "<filename_without_py>:app"
        host=host,
        port=port,
        reload=reload_opt,
        log_level=os.getenv("APP_LOG_LEVEL", "info"),
    )
