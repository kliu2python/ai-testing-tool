"""FastAPI application exposing the AI testing tool as a service."""

from __future__ import annotations

import json
import os
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from redis.asyncio import Redis

from task_queue import (
    create_async_redis_client,
    dump_status,
    load_status,
    queue_key,
    status_key,
)


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
    """Response payload containing the queued task identifier."""

    task_id: str


class TaskStatus(str, Enum):
    """Possible lifecycle states for a queued task."""

    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class TaskStatusResponse(BaseModel):
    """Status payload returned when querying for a task."""

    task_id: str
    status: TaskStatus
    summary: Optional[List[Dict[str, Any]]] = None
    summary_path: Optional[str] = None
    error: Optional[str] = None


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
async def _init_redis() -> None:
    """Create a shared Redis client for request handlers."""

    app.state.redis = create_async_redis_client()


@app.on_event("shutdown")
async def _close_redis() -> None:
    """Dispose of the Redis client on shutdown."""

    redis: Optional[Redis] = getattr(app.state, "redis", None)
    if redis is not None:
        await redis.close()


def _redis_client() -> Redis:
    """Return the application-wide Redis client instance."""

    redis: Optional[Redis] = getattr(app.state, "redis", None)
    if redis is None:
        raise HTTPException(status_code=503, detail="Redis client is unavailable")
    return redis


@app.on_event("startup")
def _ensure_reports_folder() -> None:
    # Create the default reports folder up front so writes won't fail.
    default_reports = "./reports"
    try:
        os.makedirs(default_reports, exist_ok=True)
    except Exception as exc:  # pragma: no cover
        # Not fatal; individual runs also try to create their own paths.
        print(
            f"[WARN] Failed to create default reports folder '{default_reports}': {exc}"
        )


@app.get("/", summary="Health check")
def read_root() -> Dict[str, str]:
    """Return a simple status response indicating the API is online."""
    return {"status": "ok"}


@app.post("/run", response_model=RunResponse, summary="Run automation tasks")
async def run_automation(request: RunRequest) -> RunResponse:
    """Enqueue automation tasks to be executed by the background runner."""

    redis = _redis_client()
    task_id = uuid.uuid4().hex
    payload = request.dict()
    payload["task_id"] = task_id

    try:
        await redis.set(
            status_key(task_id),
            dump_status({"status": TaskStatus.pending.value}),
        )
        await redis.rpush(queue_key(), json.dumps(payload))
    except Exception as exc:  # pragma: no cover - operational failure propagation
        raise HTTPException(
            status_code=503,
            detail=f"Failed to enqueue task: {exc}",
        ) from exc

    return RunResponse(task_id=task_id)


async def _fetch_task_status(task_id: str) -> TaskStatusResponse:
    """Load the task status payload from Redis and validate it."""

    redis = _redis_client()
    try:
        raw_status = await redis.get(status_key(task_id))
    except Exception as exc:  # pragma: no cover - operational failure propagation
        raise HTTPException(
            status_code=503, detail=f"Failed to read task status: {exc}"
        ) from exc

    if raw_status is None:
        raise HTTPException(status_code=404, detail="Unknown task id")

    data = load_status(raw_status)
    return TaskStatusResponse(task_id=task_id, **data)


@app.get(
    "/tasks/{task_id}",
    response_model=TaskStatusResponse,
    summary="Retrieve current task status",
)
async def get_task_status(task_id: str) -> TaskStatusResponse:
    """Return the latest status information for ``task_id``."""

    return await _fetch_task_status(task_id)


@app.get(
    "/tasks/{task_id}/result",
    response_model=TaskStatusResponse,
    summary="Retrieve final task result",
)
async def get_task_result(task_id: str) -> TaskStatusResponse:
    """Return the final result once the task has completed."""

    status = await _fetch_task_status(task_id)
    if status.status in {TaskStatus.pending, TaskStatus.running}:
        raise HTTPException(status_code=202, detail="Task is still in progress")
    return status


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
