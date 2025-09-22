"""FastAPI application exposing the AI testing tool as a service."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import secrets
import sqlite3
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field
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


class TaskCollectionResponse(BaseModel):
    """Grouping of task identifiers keyed by their lifecycle status."""

    completed: List[str] = Field(default_factory=list)
    pending: List[str] = Field(default_factory=list)
    running: List[str] = Field(default_factory=list)
    error: List[str] = Field(default_factory=list)


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
    StaticFiles(directory=_REPORTS_ROOT, html=False, check_dir=False),
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
        warning = "[WARN] Failed to create reports folder '%s': %s" % (
            _REPORTS_ROOT,
            exc,
        )
        print(warning)


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
    task_id = uuid.uuid4().hex
    payload = request.dict()
    payload["task_id"] = task_id
    payload["user_id"] = current_user.id

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

    return RunResponse(task_id=task_id)


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

    if raw_status is None:
        raise HTTPException(status_code=404, detail="Unknown task id")

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


async def _collect_tasks_by_status(user: User) -> TaskCollectionResponse:
    """Return all known task identifiers grouped by their status."""

    redis = _redis_client()
    prefix = status_key("")
    grouped: Dict[str, List[str]] = {
        "completed": [],
        "pending": [],
        "running": [],
        "error": [],
    }

    try:
        async for key in redis.scan_iter(match=f"{prefix}*"):
            raw_status = await redis.get(key)
            if raw_status is None:
                continue
            data = load_status(raw_status)
            owner_id = data.get("user_id")
            if not user.is_admin and owner_id != user.id:
                continue

            status_value = data.get("status")
            task_id = key.removeprefix(prefix)

            if status_value == TaskStatus.completed.value:
                grouped["completed"].append(task_id)
            elif status_value == TaskStatus.pending.value:
                grouped["pending"].append(task_id)
            elif status_value == TaskStatus.running.value:
                grouped["running"].append(task_id)
            elif status_value == TaskStatus.failed.value:
                grouped["error"].append(task_id)
    except Exception as exc:  # pragma: no cover - operational failure
        raise HTTPException(
            status_code=503, detail=f"Failed to list tasks: {exc}"
        ) from exc

    return TaskCollectionResponse(**grouped)


def _step_candidates(directory: Path) -> Iterable[Path]:
    """Yield potential screenshot files from ``directory``."""

    for extension in ("png", "jpg", "jpeg"):
        yield from directory.glob(f"step_*.{extension}")


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
        match = re.search(r"step_(\d+)", candidate.name)
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

    uvicorn.run(
        "api:app",
        host=host,
        port=port,
        reload=reload_opt,
        log_level=os.getenv("APP_LOG_LEVEL", "info"),
    )
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
