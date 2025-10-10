"""FastAPI application exposing the backend server as a service."""

from __future__ import annotations

import asyncio
from asyncio.subprocess import PIPE
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import sqlite3
import sys
import tempfile
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

import logging

from fastapi import Depends, FastAPI, Header, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field, ValidationError, model_validator
from redis.asyncio import Redis

from backend_server.example_bootstrap import (
    hash_task,
    load_example_config,
    normalise_code,
    sanitize_text,
    score_human,
    score_metrics,
)
from backend_server.libraries.codegen import (
    CodegenError,
    async_generate_pytest_from_path,
    generate_pytest_from_summary,
)
from backend_server.task_queue import (
    create_async_redis_client,
    dump_status,
    load_status,
    queue_key,
    status_key,
)
from backend_server.task_store import (
    delete_codegen_result,
    delete_task_run,
    ensure_task_tables,
    list_codegen_results,
    list_task_runs_for_user,
    load_codegen_result,
    load_latest_task_request,
    load_task_metadata,
    load_task_run,
    load_example_by_code_hash,
    record_codegen_execution,
    register_task_run,
    set_task_status,
    store_codegen_result,
    update_example_metrics,
    update_task_request,
)

logger = logging.getLogger(__name__)


def _decode_stream(payload: bytes) -> str:
    """Decode ``payload`` into UTF-8 text with replacement handling."""

    return payload.decode("utf-8", errors="replace")


# -----------------------------
# Database & Auth helpers
# -----------------------------


@dataclass
class User:
    """Authenticated API consumer."""

    id: str
    email: str
    role: str

    @property
    def is_admin(self) -> bool:
        """Return ``True`` when the user has administrative permissions."""

        return self.role.lower() == "admin"


class UserResponse(BaseModel):
    """Public user payload returned to clients."""

    id: str
    email: EmailStr
    role: str


class AuthResponse(BaseModel):
    """Authentication payload containing a bearer token."""

    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class SignUpRequest(BaseModel):
    """Payload for registering a new user."""

    email: EmailStr
    password: str = Field(..., min_length=8)


class LoginRequest(BaseModel):
    """Payload for authenticating an existing user."""

    email: EmailStr
    password: str


_PACKAGE_ROOT = Path(__file__).resolve().parent
_DB_PATH = Path(os.getenv("AITOOL_DB_PATH", str(_PACKAGE_ROOT / "auth.db")))
_REPORTS_ROOT = Path(
    os.getenv("REPORTS_ROOT", str(_PACKAGE_ROOT / "reports"))
).resolve()


def _init_database() -> None:
    """Create the SQLite database used for authentication."""

    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user'
            );

            CREATE TABLE IF NOT EXISTS auth_tokens (
                token TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            """
        )
        ensure_task_tables(conn)
        conn.commit()
    finally:
        conn.close()


def _hash_password(password: str, salt: str) -> str:
    """Derive a secure hash for ``password`` using ``salt``."""

    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 150_000
    )
    return digest.hex()


def _create_user(email: str, password: str) -> User:
    """Persist a new user in the database."""

    user_id = uuid.uuid4().hex
    salt = secrets.token_hex(16)
    password_hash = _hash_password(password, salt)

    conn = sqlite3.connect(_DB_PATH)
    try:
        conn.execute(
            (
                "INSERT INTO users (id, email, password_hash, salt) "
                "VALUES (?, ?, ?, ?)"
            ),
            (user_id, email.lower(), password_hash, salt),
        )
        conn.commit()
    except sqlite3.IntegrityError as exc:  # pragma: no cover - uniqueness guard
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        ) from exc
    finally:
        conn.close()

    return User(id=user_id, email=email.lower(), role="user")


def _get_user_by_email(email: str) -> Optional[sqlite3.Row]:
    """Return the raw database row for ``email`` if present."""

    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        query = " ".join(
            [
                "SELECT id, email, role, password_hash, salt",
                "FROM users WHERE email=?",
            ]
        )
        cursor = conn.execute(query, (email.lower(),))
        return cursor.fetchone()
    finally:
        conn.close()


def _list_all_users() -> List[sqlite3.Row]:
    """Return all registered users ordered by email."""

    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(
            "SELECT id, email, role FROM users ORDER BY email COLLATE NOCASE"
        )
        return list(cursor.fetchall())
    finally:
        conn.close()


def _authenticate_user(email: str, password: str) -> User:
    """Validate credentials and return the authenticated user."""

    row = _get_user_by_email(email)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    expected = _hash_password(password, row["salt"])
    if secrets.compare_digest(expected, row["password_hash"]) is False:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    return User(id=row["id"], email=row["email"], role=row["role"])


def _store_token(user: User) -> str:
    """Create and persist a bearer token for ``user``."""

    token = secrets.token_urlsafe(32)
    now = dt.datetime.utcnow().isoformat()
    conn = sqlite3.connect(_DB_PATH)
    try:
        conn.execute(
            (
                "INSERT INTO auth_tokens (token, user_id, created_at) "
                "VALUES (?, ?, ?)"
            ),
            (token, user.id, now),
        )
        conn.commit()
    finally:
        conn.close()
    return token


def _row_to_user(row: sqlite3.Row) -> User:
    """Convert a database row into a :class:`User`."""

    return User(id=row["id"], email=row["email"], role=row["role"])


def _token_lookup(token: str) -> Optional[User]:
    """Return the :class:`User` associated with ``token`` if valid."""

    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(
            """
            SELECT users.id, users.email, users.role
            FROM auth_tokens
            JOIN users ON users.id = auth_tokens.user_id
            WHERE auth_tokens.token = ?
            """,
            (token,),
        )
        row = cursor.fetchone()
    finally:
        conn.close()

    if row is None:
        return None
    return _row_to_user(row)


def _delete_token(token: str) -> None:
    """Remove ``token`` from the database."""

    conn = sqlite3.connect(_DB_PATH)
    try:
        conn.execute("DELETE FROM auth_tokens WHERE token = ?", (token,))
        conn.commit()
    finally:
        conn.close()


def _user_payload(user: User) -> UserResponse:
    """Return a serialisable representation of ``user``."""

    return UserResponse(id=user.id, email=user.email, role=user.role)


def _parse_bearer_token(authorization: str) -> str:
    """Extract the bearer token from the ``Authorization`` header."""

    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header",
        )
    return parts[1]


async def get_current_user(authorization: str = Header(...)) -> User:
    """FastAPI dependency that resolves the authenticated user."""

    token = _parse_bearer_token(authorization)
    user = _token_lookup(token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    return user


async def get_admin_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Ensure ``current_user`` has administrative privileges."""

    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user


# -----------------------------
# Models
# -----------------------------
class Platform(str, Enum):
    """Supported automation platforms."""

    android = "android"
    ios = "ios"
    web = "web"


class TargetConfig(BaseModel):
    """Automation target definition for multi-platform runs."""

    name: str = Field(..., description="Unique alias used to reference the target.")
    platform: Platform = Field(..., description="Platform handled by this target.")
    server: Optional[str] = Field(
        None,
        description=(
            "Automation server URL for this target. Defaults to the top-level "
            "`server` value when omitted."
        ),
    )
    default: bool = Field(
        False,
        description="Mark this target as the default context for autonomous steps.",
    )


class LlmMode(str, Enum):
    """Inference modes for the action generation model."""

    auto = "auto"
    text = "text"
    vision = "vision"


class RunRequest(BaseModel):
    """Request payload for running automation tasks."""

    prompt: str = Field(..., description="System prompt guiding the agent.")
    tasks: List[Dict[str, Any]] = Field(
        ..., description="List of task definitions to execute."
    )
    server: Optional[str] = Field(
        default=None,
        description="Automation server address (e.g., Appium/Selenium).",
    )
    platform: Optional[Platform] = Field(
        default=None,
        description="Platform against which to run the tasks.",
    )
    targets: Optional[List[TargetConfig]] = Field(
        default=None,
        description=(
            "Optional list of automation targets to initialise. When provided, "
            "the entries override the top-level `server`/`platform` configuration "
            "and allow cross-platform coordination."
        ),
    )
    reports_folder: str = Field(
        "./reports",
        description="Destination folder for generated reports.",
    )
    debug: bool = Field(
        False,
        description="Enable interactive debug mode requiring manual input.",
    )
    repeat: int = Field(
        1,
        ge=1,
        le=500,
        description="Number of times to enqueue the same task run.",
    )
    llm_mode: LlmMode = Field(
        LlmMode.auto,
        description="Preferred model mode: auto-select, text-only, or vision-enabled.",
    )

    @model_validator(mode="after")
    def _ensure_platform_or_targets(self) -> "RunRequest":
        # normalize server
        if isinstance(self.server, str):
            self.server = self.server.strip() or None

        has_targets = bool(self.targets)

        # Require platform/server only when no explicit targets exist
        if not has_targets and self.platform is None:
            raise ValueError(
                "A platform must be provided when no automation targets are configured"
            )

        if not has_targets and not self.server:
            raise ValueError(
                "An automation server must be provided when no targets are configured"
            )

        # Optional: backfill per-target server from top-level if omitted
        if has_targets and self.server:
            for t in self.targets:
                if t.server is None:
                    t.server = self.server

        return self


class RunResponse(BaseModel):
    """Response payload containing the queued task identifier."""

    task_id: str
    task_ids: List[str]


class PytestCodegenRequest(BaseModel):
    """Payload for requesting pytest code generation from a summary."""

    summary: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Automation summary payload mirroring the stored summary.json file.",
    )
    summary_path: Optional[str] = Field(
        default=None,
        description="Filesystem path to an existing summary.json file.",
    )
    task_name: Optional[str] = Field(
        default=None,
        description="Name of the scenario to convert. Takes precedence over task_index.",
    )
    task_index: int = Field(
        default=0,
        ge=0,
        description="Zero-based index of the scenario entry within the summary list.",
    )
    model: Optional[str] = Field(
        default=None,
        description="Override the OpenAI model used for code generation.",
    )
    temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        description="Sampling temperature applied to the LLM request.",
    )
    max_output_tokens: Optional[int] = Field(
        default=None,
        ge=1,
        le=8192,
        description="Optional upper bound for generated tokens.",
    )

    @model_validator(mode="after")
    def _ensure_source(self) -> "PytestCodegenRequest":
        if self.summary and self.summary_path:
            raise ValueError("Provide either 'summary' or 'summary_path', not both")
        if not self.summary and not self.summary_path:
            raise ValueError("Either 'summary' or 'summary_path' must be supplied")
        return self


class PytestCodegenResponse(BaseModel):
    """Result returned after generating pytest automation code."""

    record_id: int
    code: str
    model: str
    task_name: Optional[str] = None
    task_index: int
    function_name: Optional[str] = None


class CodegenRecordSummary(BaseModel):
    """Metadata describing a stored code generation result."""

    id: int
    task_name: Optional[str] = None
    task_index: int
    model: Optional[str] = None
    function_name: Optional[str] = None
    summary_path: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    success_count: int = 0
    failure_count: int = 0


class CodegenRecordDetail(CodegenRecordSummary):
    """Detailed payload for a stored code generation result."""

    code: str
    summary_json: Optional[Dict[str, Any]] = None
    human_score: Optional[float] = None
    example_score: Optional[float] = None
    example_metrics: Optional[Dict[str, float]] = None


class HumanScoreRequest(BaseModel):
    """Payload for recording human feedback on generated code."""

    score: float = Field(
        ..., description="Human supplied rating in the range [-1.0, 1.0]."
    )


class HumanScoreResponse(BaseModel):
    """Response payload after persisting a human feedback score."""

    record_id: int
    human_score: float
    example_score: float
    metrics: Dict[str, float]


class PytestExecutionResponse(BaseModel):
    """Payload returned after executing a stored pytest module."""

    record_id: int
    exit_code: int
    stdout: str
    stderr: str
    started_at: str
    finished_at: str
    duration_seconds: float


class TaskStatus(str, Enum):
    """Possible lifecycle states for a queued task."""

    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class StepInfo(BaseModel):
    """Metadata for an execution step screenshot."""

    index: int
    filename: str
    image_url: str


class TaskStatusResponse(BaseModel):
    """Status payload returned when querying for a task."""

    task_id: str
    status: TaskStatus
    summary: Optional[List[Dict[str, Any]]] = None
    summary_path: Optional[str] = None
    error: Optional[str] = None
    owner_id: Optional[str] = None
    steps: Optional[List[StepInfo]] = None


class TaskListEntry(BaseModel):
    """Lightweight reference to a queued automation run."""

    task_id: str = Field(..., description="Unique identifier for the queued task.")
    task_name: str = Field(..., description="Declared name of the queued task.")
    created_at: Optional[str] = Field(
        default=None,
        description="ISO 8601 timestamp recording when the task was queued.",
    )
    updated_at: Optional[str] = Field(
        default=None,
        description="ISO 8601 timestamp recording the last known update.",
    )
    owner_id: Optional[str] = Field(
        default=None,
        description="Identifier of the user who owns this task (admin only).",
    )


class TaskCollectionResponse(BaseModel):
    """Grouping of task identifiers keyed by their lifecycle status."""

    completed: List[TaskListEntry] = Field(default_factory=list)
    pending: List[TaskListEntry] = Field(default_factory=list)
    running: List[TaskListEntry] = Field(default_factory=list)
    error: List[TaskListEntry] = Field(default_factory=list)


class TaskStatusCounts(BaseModel):
    """Simple counter set for task statuses."""

    pending: int = 0
    running: int = 0
    completed: int = 0
    error: int = 0


class AdminUserTaskOverview(BaseModel):
    """Administrative payload describing a user's tasks."""

    user: UserResponse
    tasks: TaskCollectionResponse
    total_tasks: int
    status_counts: TaskStatusCounts


# -----------------------------
# App
# -----------------------------
app = FastAPI(
    title="AI Testing Tool API",
    version="1.0.0",
    description=(
        "Run cross-platform automation tasks (Android/iOS/Web) via an AI agent."
    ),
)

# CORS (adjust origins as needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ALLOW_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount(
    "/reports",
    StaticFiles(directory=str(_REPORTS_ROOT), html=False, check_dir=False),
    name="reports",
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
        raise HTTPException(
            status_code=503,
            detail="Redis client is unavailable",
        )
    return redis


@app.on_event("startup")
def _ensure_reports_folder() -> None:
    """Create the reports directory eagerly to avoid runtime errors."""

    try:
        _REPORTS_ROOT.mkdir(parents=True, exist_ok=True)
    except Exception as exc:  # pragma: no cover - filesystem issue
        logger.warning("Failed to create reports folder '%s': %s", _REPORTS_ROOT, exc)


@app.on_event("startup")
def _setup_database() -> None:
    """Initialise the SQLite database on application startup."""

    _init_database()


@app.get("/", summary="Health check")
def read_root() -> Dict[str, str]:
    """Return a simple status response indicating the API is online."""
    return {"status": "ok"}


@app.post(
    "/auth/signup",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
def signup(payload: SignUpRequest) -> AuthResponse:
    """Create a new user account and return an access token."""

    user = _create_user(payload.email, payload.password)
    token = _store_token(user)
    return AuthResponse(access_token=token, user=_user_payload(user))


@app.post(
    "/auth/login",
    response_model=AuthResponse,
    summary="Authenticate and receive an access token",
)
def login(payload: LoginRequest) -> AuthResponse:
    """Authenticate an existing user and issue a bearer token."""

    user = _authenticate_user(payload.email, payload.password)
    token = _store_token(user)
    return AuthResponse(access_token=token, user=_user_payload(user))


@app.post(
    "/auth/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke the current access token",
)
def logout(authorization: str = Header(...)) -> None:
    """Invalidate the token provided in the ``Authorization`` header."""

    token = _parse_bearer_token(authorization)
    _delete_token(token)


@app.get(
    "/auth/me",
    response_model=UserResponse,
    summary="Retrieve the authenticated user's profile",
)
async def read_profile(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Return the basic profile information for the active user."""

    return _user_payload(current_user)


@app.post("/run", response_model=RunResponse, summary="Run automation tasks")
async def run_automation(
    request: RunRequest, current_user: User = Depends(get_current_user)
) -> RunResponse:
    """Enqueue automation tasks to be executed by the background runner."""

    redis = _redis_client()
    request_payload = request.dict(exclude_none=True)
    repeat = max(1, request_payload.get("repeat", 1))
    base_payload = dict(request_payload)
    base_payload.pop("repeat", None)
    base_payload["user_id"] = current_user.id

    task_ids: List[str] = []

    for _ in range(repeat):
        task_id = uuid.uuid4().hex
        payload = dict(base_payload)
        payload["task_id"] = task_id

        try:
            register_task_run(
                task_id,
                current_user.id,
                request.reports_folder,
                request.tasks,
                request_payload=request_payload,
            )
        except sqlite3.Error as exc:  # pragma: no cover - operational failure
            message = f"Failed to persist task metadata: {exc}"
            raise HTTPException(status_code=503, detail=message) from exc

        try:
            await redis.set(
                status_key(task_id),
                dump_status(
                    {
                        "status": TaskStatus.pending.value,
                        "user_id": current_user.id,
                    }
                ),
            )
            await redis.rpush(queue_key(), json.dumps(payload))
        except Exception as exc:  # pragma: no cover - enqueue failure
            message = f"Failed to enqueue task: {exc}"
            raise HTTPException(status_code=503, detail=message) from exc

        task_ids.append(task_id)

    return RunResponse(task_id=task_ids[0], task_ids=task_ids)


@app.post(
    "/codegen/pytest",
    response_model=PytestCodegenResponse,
    summary="Generate pytest automation code from a run summary",
)
async def generate_pytest_code(
    request: PytestCodegenRequest, current_user: User = Depends(get_current_user)
) -> PytestCodegenResponse:
    """Convert an automation run summary into an executable pytest module."""

    summary_snapshot: Optional[Dict[str, Any]] = None
    summary_source_path: Optional[str] = request.summary_path

    if request.summary_path:
        try:
            result = await async_generate_pytest_from_path(
                request.summary_path,
                task_name=request.task_name,
                task_index=request.task_index,
                model=request.model,
                temperature=request.temperature,
                max_output_tokens=request.max_output_tokens,
            )
        except CodegenError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # pragma: no cover - operational failure
            logger.exception(
                "Failed to generate pytest code from summary '%s': %s",
                request.summary_path,
                exc,
            )
            raise HTTPException(
                status_code=503, detail="Failed to generate pytest code"
            ) from exc
        task_name = result.task_name or request.task_name
    else:
        summary_payload = request.summary or {}
        if request.summary is not None:
            summary_snapshot = request.summary
        if isinstance(summary_payload, dict) and summary_source_path is None:
            summary_value = summary_payload.get("summary_path")
            if isinstance(summary_value, str):
                summary_source_path = summary_value
        try:
            result = await asyncio.to_thread(
                generate_pytest_from_summary,
                summary_payload,
                task_name=request.task_name,
                task_index=request.task_index,
                model=request.model,
                temperature=request.temperature,
                max_output_tokens=request.max_output_tokens,
            )
        except CodegenError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # pragma: no cover - operational failure
            logger.exception("Failed to generate pytest code: %s", exc)
            raise HTTPException(
                status_code=503, detail="Failed to generate pytest code"
            ) from exc

        task_name = result.task_name or request.task_name
        if not task_name:
            summary_list = summary_payload.get("summary") if isinstance(
                summary_payload, dict
            ) else None
            if (
                isinstance(summary_list, list)
                and 0 <= request.task_index < len(summary_list)
                and isinstance(summary_list[request.task_index], dict)
            ):
                task_name = summary_list[request.task_index].get("name")

    try:
        record_id = store_codegen_result(
            current_user.id,
            task_name=task_name,
            task_index=request.task_index,
            model=result.model,
            code=result.code,
            function_name=result.function_name,
            summary_path=summary_source_path,
            summary_json=summary_snapshot,
        )
    except sqlite3.Error as exc:  # pragma: no cover - operational failure
        logger.exception("Failed to persist generated pytest code: %s", exc)
        raise HTTPException(
            status_code=503, detail="Failed to store generated code"
        ) from exc

    return PytestCodegenResponse(
        record_id=record_id,
        code=result.code,
        model=result.model,
        task_name=task_name,
        task_index=request.task_index,
        function_name=result.function_name,
    )


@app.get(
    "/codegen/pytest",
    response_model=List[CodegenRecordSummary],
    summary="List stored pytest code generation results",
)
async def list_codegen_history(
    current_user: User = Depends(get_current_user),
) -> List[CodegenRecordSummary]:
    """Return all stored code generation results visible to the user."""

    owner_filter = None if current_user.is_admin else current_user.id
    try:
        records = list_codegen_results(owner_filter)
    except sqlite3.Error as exc:  # pragma: no cover - operational failure
        logger.exception("Failed to list stored code: %s", exc)
        raise HTTPException(
            status_code=503, detail="Failed to load stored code"
        ) from exc

    return [
        CodegenRecordSummary(
            id=record["id"],
            task_name=record.get("task_name"),
            task_index=record.get("task_index", 0),
            model=record.get("model"),
            function_name=record.get("function_name"),
            summary_path=record.get("summary_path"),
            created_at=record.get("created_at"),
            updated_at=record.get("updated_at"),
            success_count=record.get("success_count", 0),
            failure_count=record.get("failure_count", 0),
        )
        for record in records
    ]


@app.get(
    "/codegen/pytest/{record_id}",
    response_model=CodegenRecordDetail,
    summary="Retrieve a stored pytest code generation result",
)
async def get_codegen_history_entry(
    record_id: int, current_user: User = Depends(get_current_user)
) -> CodegenRecordDetail:
    """Return the stored code for ``record_id`` if permitted."""

    try:
        record = load_codegen_result(record_id)
    except sqlite3.Error as exc:  # pragma: no cover - operational failure
        logger.exception("Failed to load stored code %s: %s", record_id, exc)
        raise HTTPException(
            status_code=503, detail="Failed to load stored code"
        ) from exc

    if record is None:
        raise HTTPException(status_code=404, detail="Generated code not found")

    if not current_user.is_admin and record.get("user_id") != current_user.id:
        raise HTTPException(status_code=403, detail="Generated code is not accessible")

    human_score_value: Optional[float] = None
    example_score_value: Optional[float] = None
    example_metrics: Optional[Dict[str, float]] = None
    code_text = record.get("code", "")
    if code_text:
        try:
            sanitized_code = sanitize_text(code_text)
            code_hash = hash_task("code", normalise_code(sanitized_code))
            example = load_example_by_code_hash(code_hash)
        except sqlite3.Error as exc:  # pragma: no cover - operational failure
            logger.exception(
                "Failed to load example metrics for code %s: %s", record_id, exc
            )
        else:
            if example:
                metrics = {
                    key: float(value) for key, value in (example.get("metrics") or {}).items()
                }
                example_metrics = metrics
                human_score_value = metrics.get("human_score")
                example_score_value = float(example.get("score", 0.0))

    return CodegenRecordDetail(
        id=record["id"],
        task_name=record.get("task_name"),
        task_index=record.get("task_index", 0),
        model=record.get("model"),
        function_name=record.get("function_name"),
        summary_path=record.get("summary_path"),
        created_at=record.get("created_at"),
        updated_at=record.get("updated_at"),
        code=record.get("code", ""),
        summary_json=record.get("summary_json"),
        success_count=record.get("success_count", 0),
        failure_count=record.get("failure_count", 0),
        human_score=human_score_value,
        example_score=example_score_value,
        example_metrics=example_metrics,
    )


@app.delete(
    "/codegen/pytest/{record_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a stored pytest code generation result",
)
async def delete_codegen_history_entry(
    record_id: int, current_user: User = Depends(get_current_user)
) -> Response:
    """Remove the stored code for ``record_id`` if permitted."""

    try:
        record = load_codegen_result(record_id)
    except sqlite3.Error as exc:  # pragma: no cover - operational failure
        logger.exception("Failed to load stored code %s: %s", record_id, exc)
        raise HTTPException(
            status_code=503, detail="Failed to delete stored code"
        ) from exc

    if record is None:
        raise HTTPException(status_code=404, detail="Generated code not found")

    if not current_user.is_admin and record.get("user_id") != current_user.id:
        raise HTTPException(status_code=403, detail="Generated code is not accessible")

    try:
        delete_codegen_result(record_id)
    except sqlite3.Error as exc:  # pragma: no cover - operational failure
        logger.exception("Failed to delete stored code %s: %s", record_id, exc)
        raise HTTPException(
            status_code=503, detail="Failed to delete stored code"
        ) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post(
    "/codegen/pytest/{record_id}/execute",
    response_model=PytestExecutionResponse,
    summary="Execute a stored pytest module",
)
async def execute_codegen_history_entry(
    record_id: int, current_user: User = Depends(get_current_user)
) -> PytestExecutionResponse:
    """Run the stored pytest module identified by ``record_id``."""

    try:
        record = load_codegen_result(record_id)
    except sqlite3.Error as exc:  # pragma: no cover - operational failure
        logger.exception("Failed to load stored code %s: %s", record_id, exc)
        raise HTTPException(
            status_code=503, detail="Failed to load stored code"
        ) from exc

    if record is None:
        raise HTTPException(status_code=404, detail="Generated code not found")

    if not current_user.is_admin and record.get("user_id") != current_user.id:
        raise HTTPException(status_code=403, detail="Generated code is not accessible")

    code = record.get("code")
    if not isinstance(code, str) or not code.strip():
        raise HTTPException(status_code=400, detail="Stored code is empty")

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            module_path = Path(tmpdir) / "test_generated.py"
            module_path.write_text(code, encoding="utf-8")
            started_at = dt.datetime.utcnow()
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "pytest",
                str(module_path),
                stdout=PIPE,
                stderr=PIPE,
                cwd=tmpdir,
            )
            stdout_bytes, stderr_bytes = await process.communicate()
            finished_at = dt.datetime.utcnow()
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503, detail=f"Failed to execute pytest: {exc}"
        ) from exc
    except Exception as exc:  # pragma: no cover - operational failure
        logger.exception("Failed to execute stored pytest module %s: %s", record_id, exc)
        raise HTTPException(
            status_code=503, detail="Failed to execute generated code"
        ) from exc

    duration = max((finished_at - started_at).total_seconds(), 0.0)
    exit_code = process.returncode or 0

    try:
        record_codegen_execution(record_id, exit_code == 0)
    except sqlite3.Error as exc:  # pragma: no cover - operational failure
        logger.exception(
            "Failed to update execution counters for %s: %s", record_id, exc
        )

    return PytestExecutionResponse(
        record_id=record_id,
        exit_code=exit_code,
        stdout=_decode_stream(stdout_bytes),
        stderr=_decode_stream(stderr_bytes),
        started_at=started_at.isoformat(),
        finished_at=finished_at.isoformat(),
        duration_seconds=duration,
    )


@app.post(
    "/codegen/pytest/{record_id}/human-score",
    response_model=HumanScoreResponse,
    summary="Record a human feedback score for a generated pytest module",
)
async def set_codegen_human_score(
    record_id: int,
    request: HumanScoreRequest,
    current_user: User = Depends(get_current_user),
) -> HumanScoreResponse:
    """Persist a normalised human feedback score for the selected record."""

    try:
        record = load_codegen_result(record_id)
    except sqlite3.Error as exc:  # pragma: no cover - operational failure
        logger.exception("Failed to load stored code %s: %s", record_id, exc)
        raise HTTPException(
            status_code=503, detail="Failed to load stored code"
        ) from exc

    if record is None:
        raise HTTPException(status_code=404, detail="Generated code not found")

    if not current_user.is_admin and record.get("user_id") != current_user.id:
        raise HTTPException(status_code=403, detail="Generated code is not accessible")

    code_text = record.get("code")
    if not code_text:
        raise HTTPException(
            status_code=400, detail="Generated code does not contain any content"
        )

    normalized_score = score_human(request.score)
    config = load_example_config()
    sanitized_code = sanitize_text(code_text)
    code_hash = hash_task("code", normalise_code(sanitized_code))

    try:
        example = load_example_by_code_hash(code_hash)
    except sqlite3.Error as exc:  # pragma: no cover - operational failure
        logger.exception(
            "Failed to load example for human score update %s: %s", record_id, exc
        )
        raise HTTPException(
            status_code=503, detail="Failed to update example score"
        ) from exc

    if not example:
        raise HTTPException(
            status_code=404,
            detail="Stored example for generated code was not found",
        )

    metrics = {
        key: float(value) for key, value in (example.get("metrics") or {}).items()
    }
    metrics["human_score"] = normalized_score
    total_score = score_metrics(metrics, config.scoring_weights)

    try:
        updated = update_example_metrics(code_hash, metrics, total_score)
    except sqlite3.Error as exc:  # pragma: no cover - operational failure
        logger.exception(
            "Failed to persist human score for %s: %s", record_id, exc
        )
        raise HTTPException(status_code=503, detail="Failed to store human score") from exc

    if not updated:
        raise HTTPException(
            status_code=404,
            detail="Stored example for generated code was not found",
        )

    return HumanScoreResponse(
        record_id=record_id,
        human_score=normalized_score,
        example_score=total_score,
        metrics=metrics,
    )


async def _fetch_task_status(
    task_id: str,
    current_user: User,
) -> TaskStatusResponse:
    """Load the task status payload from Redis and validate it."""

    redis = _redis_client()
    try:
        raw_status = await redis.get(status_key(task_id))
    except Exception as exc:  # pragma: no cover - operational failure
        raise HTTPException(
            status_code=503, detail=f"Failed to read task status: {exc}"
        ) from exc

    if raw_status is not None:
        data = load_status(raw_status)
        owner_id = data.pop("user_id", None)
        if owner_id is None and not current_user.is_admin:
            raise HTTPException(status_code=403, detail="Task is not accessible")
        if not current_user.is_admin and owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="Task is not accessible")

        return TaskStatusResponse(
            task_id=task_id,
            owner_id=owner_id,
            **data,
        )

    record = load_task_run(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Unknown task id")

    owner_id = record.get("user_id")
    if owner_id is None and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Task is not accessible")
    if not current_user.is_admin and owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Task is not accessible")

    try:
        status_value = TaskStatus(record.get("status", TaskStatus.pending.value))
    except ValueError as exc:  # pragma: no cover - defensive guard
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return TaskStatusResponse(
        task_id=task_id,
        status=status_value,
        summary=record.get("summary"),
        summary_path=record.get("summary_path"),
        error=record.get("error"),
        owner_id=owner_id,
    )


async def _collect_tasks_by_status(
    user: User,
    owner_id: Optional[str] = None,
    *,
    include_owner: bool = False,
) -> TaskCollectionResponse:
    """Return known task identifiers grouped by status with optional filtering."""

    if owner_id is not None and not user.is_admin and owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorised to view tasks for this user",
        )

    owner_filter = (
        owner_id
        if owner_id is not None
        else (None if user.is_admin else user.id)
    )
    reveal_owner = include_owner or (owner_filter is None and user.is_admin)

    redis = _redis_client()
    prefix = status_key("")
    grouped: Dict[str, List[TaskListEntry]] = {
        "completed": [],
        "pending": [],
        "running": [],
        "error": [],
    }
    redis_records: Dict[str, Dict[str, Optional[str]]] = {}

    try:
        async for key in redis.scan_iter(match=f"{prefix}*"):
            raw_status = await redis.get(key)
            if raw_status is None:
                continue
            data = load_status(raw_status)
            task_owner = data.get("user_id")
            if owner_filter is not None and task_owner != owner_filter:
                continue

            status_value = data.get("status")
            task_id = key.removeprefix(prefix)
            if status_value:
                redis_records[task_id] = {
                    "status": status_value,
                    "owner_id": task_owner,
                }
    except Exception as exc:  # pragma: no cover - operational failure
        raise HTTPException(
            status_code=503, detail=f"Failed to list tasks: {exc}"
        ) from exc

    try:
        records = list_task_runs_for_user(owner_filter)
    except sqlite3.Error as exc:  # pragma: no cover - operational failure
        raise HTTPException(
            status_code=503, detail=f"Failed to load stored tasks: {exc}"
        ) from exc

    all_task_ids: Set[str] = set(redis_records)
    for record in records:
        all_task_ids.add(record["id"])

    metadata = load_task_metadata(tuple(all_task_ids))
    record_lookup = {record["id"]: record for record in records}

    def _resolve_owner(task_id: str) -> Optional[str]:
        record = record_lookup.get(task_id)
        if record is not None and record.get("user_id"):
            return record.get("user_id")
        redis_info = redis_records.get(task_id)
        if redis_info is not None and redis_info.get("owner_id"):
            return redis_info.get("owner_id")
        if owner_filter is not None:
            return owner_filter
        return None

    def _entry(task_id: str) -> TaskListEntry:
        info = metadata.get(task_id, {})
        record = record_lookup.get(task_id, {})
        name = info.get("task_name") or "unnamed"
        created_at = info.get("created_at") or record.get("created_at")
        updated_at = info.get("updated_at") or record.get("updated_at")
        return TaskListEntry(
            task_id=task_id,
            task_name=name,
            created_at=created_at,
            updated_at=updated_at,
            owner_id=_resolve_owner(task_id) if reveal_owner else None,
        )

    for task_id, redis_info in redis_records.items():
        status_value = redis_info.get("status")
        if status_value == TaskStatus.completed.value:
            grouped["completed"].append(_entry(task_id))
        elif status_value == TaskStatus.pending.value:
            grouped["pending"].append(_entry(task_id))
        elif status_value == TaskStatus.running.value:
            grouped["running"].append(_entry(task_id))
        elif status_value == TaskStatus.failed.value:
            grouped["error"].append(_entry(task_id))

    for record in records:
        task_id = record["id"]
        if task_id in redis_records:
            continue
        status_value = record.get("status", TaskStatus.pending.value)
        if status_value == TaskStatus.completed.value:
            grouped["completed"].append(_entry(task_id))
        elif status_value == TaskStatus.pending.value:
            grouped["pending"].append(_entry(task_id))
        elif status_value == TaskStatus.running.value:
            grouped["running"].append(_entry(task_id))
        elif status_value == TaskStatus.failed.value:
            grouped["error"].append(_entry(task_id))

    for entries in grouped.values():
        entries.sort(
            key=lambda entry: (entry.updated_at or entry.created_at or ""),
            reverse=True,
        )

    return TaskCollectionResponse(**grouped)


def _step_candidates(directory: Path) -> Iterable[Path]:
    """Yield potential screenshot files from ``directory``."""

    for extension in ("png", "jpg", "jpeg"):
        yield from directory.rglob(f"step*.{extension}")


def _build_step_images(summary_path: Optional[str]) -> List[StepInfo]:
    """Return ordered :class:`StepInfo` entries for ``summary_path``."""

    if not summary_path:
        return []

    try:
        summary_file = Path(summary_path).resolve()
    except (OSError, RuntimeError):  # pragma: no cover - invalid path
        return []

    directory = summary_file.parent
    if not directory.exists():
        return []

    chosen: Dict[int, Path] = {}
    for candidate in _step_candidates(directory):
        if not candidate.is_file():
            continue
        match = re.search(r"step(\d+)", candidate.name)
        if not match:
            continue
        index = int(match.group(1))
        if index in chosen:
            continue
        try:
            relative = candidate.resolve().relative_to(_REPORTS_ROOT)
        except ValueError:
            continue
        chosen[index] = relative

    step_infos: List[StepInfo] = []
    for index in sorted(chosen):
        relative = chosen[index]
        image_url = f"/reports/{relative.as_posix()}"
        step_infos.append(
            StepInfo(index=index, filename=relative.name, image_url=image_url)
        )
    return step_infos


@app.get(
    "/tasks/{task_id}",
    response_model=TaskStatusResponse,
    summary="Retrieve current task status",
)
async def get_task_status(
    task_id: str, current_user: User = Depends(get_current_user)
) -> TaskStatusResponse:
    """Return the latest status information for ``task_id``."""

    return await _fetch_task_status(task_id, current_user)


@app.get(
    "/tasks",
    response_model=TaskCollectionResponse,
    summary="List all queued tasks grouped by status",
)
async def list_tasks(
    current_user: User = Depends(get_current_user),
) -> TaskCollectionResponse:
    """Return the collection of task identifiers grouped by their status."""

    return await _collect_tasks_by_status(current_user)


@app.get(
    "/admin/users",
    response_model=List[AdminUserTaskOverview],
    summary="List all users with their task status summaries",
)
async def list_users_for_admin(
    current_user: User = Depends(get_admin_user),
) -> List[AdminUserTaskOverview]:
    """Return administrative task overviews for each registered user."""

    try:
        rows = _list_all_users()
    except sqlite3.Error as exc:  # pragma: no cover - defensive guard
        raise HTTPException(
            status_code=503, detail=f"Failed to load users: {exc}"
        ) from exc

    overviews: List[AdminUserTaskOverview] = []
    for row in rows:
        user_record = _row_to_user(row)
        tasks = await _collect_tasks_by_status(
            current_user, owner_id=user_record.id, include_owner=True
        )
        counts = TaskStatusCounts(
            pending=len(tasks.pending),
            running=len(tasks.running),
            completed=len(tasks.completed),
            error=len(tasks.error),
        )
        total = (
            counts.pending
            + counts.running
            + counts.completed
            + counts.error
        )
        overviews.append(
            AdminUserTaskOverview(
                user=_user_payload(user_record),
                tasks=tasks,
                total_tasks=total,
                status_counts=counts,
            )
        )

    return overviews


@app.get(
    "/tasks/{task_id}/result",
    response_model=TaskStatusResponse,
    summary="Retrieve final task result",
)
async def get_task_result(
    task_id: str, current_user: User = Depends(get_current_user)
) -> TaskStatusResponse:
    """Return the final result once the task has completed."""

    status = await _fetch_task_status(task_id, current_user)
    if status.status in {TaskStatus.pending, TaskStatus.running}:
        raise HTTPException(status_code=202, detail="Task is still in progress")
    steps = _build_step_images(status.summary_path)
    return status.copy(update={"steps": steps})


@app.get(
    "/tasks/{task_name}/request",
    response_model=RunRequest,
    summary="Retrieve stored task configuration",
)
async def get_task_request(
    task_name: str, current_user: User = Depends(get_current_user)
) -> RunRequest:
    """Return the most recent stored configuration for ``task_name``."""

    owner_filter = None if current_user.is_admin else current_user.id
    record = load_latest_task_request(task_name, owner_filter)
    if record is None or not record.get("payload"):
        raise HTTPException(status_code=404, detail="Task configuration not found")

    try:
        return RunRequest(**record["payload"])
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail="Stored task configuration is invalid",
        ) from exc


@app.put(
    "/tasks/{task_name}/request",
    response_model=RunRequest,
    summary="Update stored task configuration",
)
async def update_task_request_endpoint(
    task_name: str,
    request: RunRequest,
    current_user: User = Depends(get_current_user),
) -> RunRequest:
    """Persist a modified configuration for ``task_name``."""

    owner_filter = None if current_user.is_admin else current_user.id
    record = load_latest_task_request(task_name, owner_filter)
    if record is None:
        raise HTTPException(status_code=404, detail="Task configuration not found")

    if not current_user.is_admin and record.get("user_id") != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorised to modify this task")

    try:
        update_task_request(record["task_id"], request.tasks, request.dict())
    except ValueError as exc:  # pragma: no cover - defensive guard
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return request


@app.post(
    "/tasks/{task_name}/rerun",
    response_model=RunResponse,
    summary="Rerun a stored task configuration",
)
async def rerun_task_by_name(
    task_name: str, current_user: User = Depends(get_current_user)
) -> RunResponse:
    """Requeue the most recent run for ``task_name`` using stored settings."""

    owner_filter = None if current_user.is_admin else current_user.id
    record = load_latest_task_request(task_name, owner_filter)
    if record is None or not record.get("payload"):
        raise HTTPException(status_code=404, detail="Task configuration not found")

    payload = record["payload"]
    try:
        stored_request = RunRequest(**payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail="Stored task configuration is invalid",
        ) from exc

    return await run_automation(stored_request, current_user)


@app.delete(
    "/tasks/{task_id}",
    status_code=204,
    summary="Delete a task and its status",
)
async def delete_task(
    task_id: str, current_user: User = Depends(get_current_user)
) -> None:
    """Remove a queued or completed task if the user is authorised."""

    await _fetch_task_status(task_id, current_user)
    redis = _redis_client()

    try:
        queue_entries = await redis.lrange(queue_key(), 0, -1)
        for raw_entry in queue_entries:
            try:
                item = json.loads(raw_entry)
            except json.JSONDecodeError:  # pragma: no cover - malformed payload
                continue
            if item.get("task_id") == task_id:
                await redis.lrem(queue_key(), 0, raw_entry)
                break
        await redis.delete(status_key(task_id))
    except Exception as exc:  # pragma: no cover - operational failure
        raise HTTPException(
            status_code=503, detail=f"Failed to delete task: {exc}"
        ) from exc

    try:
        delete_task_run(task_id)
    except sqlite3.Error as exc:  # pragma: no cover - operational failure
        raise HTTPException(
            status_code=503, detail=f"Failed to purge stored task: {exc}"
        ) from exc


# -----------------------------
# Entrypoint
# -----------------------------
if __name__ == "__main__":
    # Environment-configurable server settings
    host = os.getenv("APP_HOST", "0.0.0.0")
    port = int(os.getenv("APP_PORT", "8090"))
    reload_opt = os.getenv("APP_RELOAD", "true").lower() in {
        "1",
        "true",
        "yes",
    }

    import uvicorn

    def _resolve_ssl_path(value: Optional[str], env_name: str) -> Optional[str]:
        """Validate and normalise SSL-related file paths from the environment."""

        if not value:
            return None

        candidate = Path(value).expanduser()
        if not candidate.is_file():
            raise SystemExit(
                f"Environment variable {env_name} references missing file: {candidate}"
            )
        return str(candidate)

    ssl_certfile = _resolve_ssl_path("./tls.crt", "tls.crt")
    ssl_keyfile = _resolve_ssl_path("./tls.key", "tls.key")
    ssl_ca_certs = _resolve_ssl_path("./ca-chain.cert.pem", "ca-chain.cert.pem")
    ssl_keyfile_password = "Fortinet123#"

    ssl_options: Dict[str, Any] = {}
    if ssl_certfile and ssl_keyfile:
        ssl_options.update(
            {
                "ssl_certfile": ssl_certfile,
                "ssl_keyfile": ssl_keyfile,
            }
        )
        if ssl_keyfile_password:
            ssl_options["ssl_keyfile_password"] = ssl_keyfile_password
        if ssl_ca_certs:
            ssl_options["ssl_ca_certs"] = ssl_ca_certs
    elif ssl_certfile or ssl_keyfile:
        raise SystemExit(
            "Both APP_SSL_CERTFILE and APP_SSL_KEYFILE must be provided to enable HTTPS."
        )
    elif ssl_ca_certs:
        raise SystemExit(
            "APP_SSL_CA_CERTS is only valid when TLS is enabled via cert and key files."
        )
    elif ssl_keyfile_password:
        raise SystemExit(
            "APP_SSL_KEYFILE_PASSWORD is only valid when TLS is enabled via cert and key files."
        )

    uvicorn.run(
        "api:app",
        host=host,
        port=port,
        reload=reload_opt,
        log_level=os.getenv("APP_LOG_LEVEL", "info"),
        **ssl_options,
    )
