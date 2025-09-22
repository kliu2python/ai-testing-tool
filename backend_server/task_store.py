"""SQLite persistence helpers for task execution metadata."""

from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence


_PACKAGE_ROOT = Path(__file__).resolve().parent
_DB_PATH = Path(os.getenv("AITOOL_DB_PATH", str(_PACKAGE_ROOT / "auth.db")))


def _connect() -> sqlite3.Connection:
    """Return a SQLite connection with foreign keys enabled."""

    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ensure_task_tables(conn: sqlite3.Connection) -> None:
    """Create task-related tables if they do not already exist."""

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS task_runs (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            status TEXT NOT NULL,
            reports_root TEXT NOT NULL,
            summary_path TEXT,
            summary_json TEXT,
            error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS task_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            name TEXT NOT NULL,
            details TEXT,
            scope TEXT,
            result_json TEXT,
            reports_path TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(run_id, name),
            FOREIGN KEY(run_id) REFERENCES task_runs(id) ON DELETE CASCADE
        );
        """
    )


def _normalise_path(path: str) -> str:
    """Return ``path`` using forward slashes without ``./`` prefixes."""

    normalised = os.path.normpath(path).replace("\\", "/")
    if normalised in {".", "/"}:
        return normalised
    if normalised.startswith("./"):
        return normalised[2:]
    return normalised


def register_task_run(
    task_id: str,
    user_id: str,
    reports_root: str,
    tasks: Sequence[Dict[str, Any]],
) -> None:
    """Persist a queued task run and its individual task entries."""

    now = dt.datetime.utcnow().isoformat()
    reports_root_norm = _normalise_path(reports_root or "./reports")

    conn = _connect()
    try:
        ensure_task_tables(conn)
        conn.execute(
            """
            INSERT INTO task_runs (
                id, user_id, status, reports_root, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                user_id=excluded.user_id,
                status=excluded.status,
                reports_root=excluded.reports_root,
                updated_at=excluded.updated_at
            """,
            (task_id, user_id, "pending", reports_root_norm, now, now),
        )

        for task in tasks:
            name = task.get("name") or "unnamed"
            details = task.get("details")
            scope = task.get("scope")
            reports_path = _normalise_path(
                os.path.join(reports_root_norm, name, task_id)
            )
            conn.execute(
                """
                INSERT INTO task_entries (
                    run_id, name, details, scope, reports_path, created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id, name) DO UPDATE SET
                    details=excluded.details,
                    scope=excluded.scope,
                    reports_path=excluded.reports_path,
                    updated_at=excluded.updated_at
                """,
                (task_id, name, details, scope, reports_path, now, now),
            )

        conn.commit()
    finally:
        conn.close()


def set_task_status(
    task_id: str,
    status: str,
    summary: Optional[List[Dict[str, Any]]] = None,
    summary_path: Optional[str] = None,
    error: Optional[str] = None,
    user_id: Optional[str] = None,
    reports_root: Optional[str] = None,
) -> None:
    """Update the stored status and results for ``task_id``."""

    now = dt.datetime.utcnow().isoformat()
    summary_json = json.dumps(summary) if summary is not None else None
    summary_path_norm = _normalise_path(summary_path) if summary_path else None
    reports_root_norm = (
        _normalise_path(reports_root) if reports_root is not None else None
    )

    conn = _connect()
    try:
        ensure_task_tables(conn)
        cursor = conn.execute(
            """
            UPDATE task_runs
               SET status = ?,
                   summary_path = ?,
                   summary_json = ?,
                   error = ?,
                   updated_at = ?
             WHERE id = ?
            """,
            (status, summary_path_norm, summary_json, error, now, task_id),
        )

        if cursor.rowcount == 0 and user_id is not None:
            conn.execute(
                """
                INSERT INTO task_runs (
                    id, user_id, status, reports_root, summary_path,
                    summary_json, error, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status = excluded.status,
                    summary_path = excluded.summary_path,
                    summary_json = excluded.summary_json,
                    error = excluded.error,
                    updated_at = excluded.updated_at
                """,
                (
                    task_id,
                    user_id,
                    status,
                    reports_root_norm or "./reports",
                    summary_path_norm,
                    summary_json,
                    error,
                    now,
                    now,
                ),
            )

        if summary is not None:
            for item in summary:
                name = item.get("name")
                if not name:
                    continue
                conn.execute(
                    """
                    UPDATE task_entries
                       SET result_json = ?,
                           updated_at = ?
                     WHERE run_id = ? AND name = ?
                    """,
                    (json.dumps(item), now, task_id, name),
                )

        conn.commit()
    finally:
        conn.close()


def load_task_run(task_id: str) -> Optional[Dict[str, Any]]:
    """Return stored information for ``task_id`` if present."""

    conn = _connect()
    try:
        ensure_task_tables(conn)
        cursor = conn.execute(
            """
            SELECT id, user_id, status, summary_path, summary_json, error
              FROM task_runs
             WHERE id = ?
            """,
            (task_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None

        summary = json.loads(row["summary_json"]) if row["summary_json"] else None
        return {
            "task_id": row["id"],
            "user_id": row["user_id"],
            "status": row["status"],
            "summary": summary,
            "summary_path": row["summary_path"],
            "error": row["error"],
        }
    finally:
        conn.close()


def load_task_names(task_ids: Sequence[str]) -> Dict[str, str]:
    """Return the declared task name for each ``task_id`` in ``task_ids``."""

    if not task_ids:
        return {}

    conn = _connect()
    try:
        ensure_task_tables(conn)
        placeholders = ",".join("?" for _ in task_ids)
        query = (
            "SELECT run_id, name FROM task_entries "
            f"WHERE run_id IN ({placeholders}) ORDER BY run_id, id"
        )
        cursor = conn.execute(query, tuple(task_ids))
        names: Dict[str, str] = {}
        for row in cursor:
            run_id = row["run_id"]
            if run_id in names:
                continue
            name = row["name"] or "unnamed"
            names[run_id] = name
        return names
    finally:
        conn.close()


def list_task_runs_for_user(user_id: Optional[str]) -> Iterable[Dict[str, str]]:
    """Yield task run identifiers and statuses for ``user_id``."""

    conn = _connect()
    try:
        ensure_task_tables(conn)
        if user_id is None:
            cursor = conn.execute(
                "SELECT id, user_id, status FROM task_runs ORDER BY created_at DESC"
            )
        else:
            cursor = conn.execute(
                """
                SELECT id, user_id, status
                  FROM task_runs
                 WHERE user_id = ?
              ORDER BY created_at DESC
                """,
                (user_id,),
            )

        for row in cursor:
            yield {"id": row["id"], "user_id": row["user_id"], "status": row["status"]}
    finally:
        conn.close()


def delete_task_run(task_id: str) -> None:
    """Remove persisted metadata for ``task_id``."""

    conn = _connect()
    try:
        ensure_task_tables(conn)
        conn.execute("DELETE FROM task_runs WHERE id = ?", (task_id,))
        conn.commit()
    finally:
        conn.close()
