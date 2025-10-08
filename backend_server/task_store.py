"""SQLite persistence helpers for task execution metadata."""

from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, TYPE_CHECKING


if TYPE_CHECKING:  # pragma: no cover - circular typing guard
    from backend_server.example_bootstrap import Example


_PACKAGE_ROOT = Path(__file__).resolve().parent
_DB_PATH = Path(os.getenv("AITOOL_DB_PATH", str(_PACKAGE_ROOT / "auth.db")))


def _connect() -> sqlite3.Connection:
    """Return a SQLite connection with foreign keys enabled."""

    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ensure_column(
    conn: sqlite3.Connection, table: str, column: str, definition: str
) -> None:
    """Add ``column`` to ``table`` when it does not yet exist."""

    cursor = conn.execute(f"PRAGMA table_info({table})")
    if column not in {row[1] for row in cursor.fetchall()}:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


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

    _ensure_column(conn, "task_runs", "request_json", "TEXT")
    conn.executescript(
        """
    CREATE TABLE IF NOT EXISTS codegen_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        task_name TEXT,
        task_index INTEGER NOT NULL DEFAULT 0,
        model TEXT,
        code TEXT NOT NULL,
        function_name TEXT,
        summary_path TEXT,
        summary_json TEXT,
        success_count INTEGER NOT NULL DEFAULT 0,
        failure_count INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """
    )

    _ensure_column(
        conn,
        "codegen_history",
        "success_count",
        "INTEGER NOT NULL DEFAULT 0",
    )
    _ensure_column(
        conn,
        "codegen_history",
        "failure_count",
        "INTEGER NOT NULL DEFAULT 0",
    )


def ensure_example_tables(conn: sqlite3.Connection) -> None:
    """Create example storage tables when absent."""

    conn.executescript(
        """
    CREATE TABLE IF NOT EXISTS code_examples (
        example_id TEXT PRIMARY KEY,
        task_hash TEXT NOT NULL,
        language TEXT NOT NULL,
        framework TEXT,
        code TEXT NOT NULL,
        summary TEXT NOT NULL,
        metrics_json TEXT NOT NULL,
        score REAL NOT NULL,
        created_at TEXT NOT NULL,
        tags_json TEXT,
        embedding_json TEXT,
        code_hash TEXT NOT NULL UNIQUE
    );

    CREATE INDEX IF NOT EXISTS idx_code_examples_language
        ON code_examples(language);

    CREATE INDEX IF NOT EXISTS idx_code_examples_framework
        ON code_examples(framework);

    CREATE INDEX IF NOT EXISTS idx_code_examples_task_hash
        ON code_examples(task_hash);
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
    request_payload: Optional[Dict[str, Any]] = None,
) -> None:
    """Persist a queued task run and its individual task entries."""

    now = dt.datetime.utcnow().isoformat()
    reports_root_norm = _normalise_path(reports_root or "./reports")

    request_json = json.dumps(request_payload) if request_payload is not None else None

    conn = _connect()
    try:
        ensure_task_tables(conn)
        conn.execute(
            """
            INSERT INTO task_runs (
                id, user_id, status, reports_root, request_json, created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                user_id=excluded.user_id,
                status=excluded.status,
                reports_root=excluded.reports_root,
                request_json=excluded.request_json,
                updated_at=excluded.updated_at
            """,
            (
                task_id,
                user_id,
                "pending",
                reports_root_norm,
                request_json,
                now,
                now,
            ),
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


def load_task_metadata(
    task_ids: Sequence[str],
) -> Dict[str, Dict[str, Optional[str]]]:
    """Return stored metadata for each ``task_id`` in ``task_ids``."""

    if not task_ids:
        return {}

    conn = _connect()
    try:
        ensure_task_tables(conn)
        placeholders = ",".join("?" for _ in task_ids)
        query = (
            """
            SELECT te.run_id,
                   te.name,
                   tr.created_at,
                   tr.updated_at
              FROM task_entries AS te
              JOIN task_runs AS tr ON te.run_id = tr.id
             WHERE te.run_id IN ({placeholders})
          ORDER BY te.run_id, te.id
            """.format(placeholders=placeholders)
        )
        cursor = conn.execute(query, tuple(task_ids))
        metadata: Dict[str, Dict[str, Optional[str]]] = {}
        for row in cursor:
            run_id = row["run_id"]
            if run_id in metadata:
                continue
            metadata[run_id] = {
                "task_name": (row["name"] or "unnamed"),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        return metadata
    finally:
        conn.close()


def load_task_names(task_ids: Sequence[str]) -> Dict[str, str]:
    """Return the declared task name for each ``task_id`` in ``task_ids``."""

    metadata = load_task_metadata(task_ids)
    return {task_id: info.get("task_name", "unnamed") for task_id, info in metadata.items()}


def load_latest_task_request(
    task_name: str, user_id: Optional[str]
) -> Optional[Dict[str, Any]]:
    """Return the most recent stored request payload for ``task_name``."""

    conn = _connect()
    try:
        ensure_task_tables(conn)
        query = (
            """
            SELECT tr.id, tr.user_id, tr.request_json
              FROM task_runs AS tr
              JOIN task_entries AS te ON te.run_id = tr.id
             WHERE te.name = ?
            """
        )
        params: List[Any] = [task_name]
        if user_id is not None:
            query += " AND tr.user_id = ?"
            params.append(user_id)
        query += " ORDER BY tr.created_at DESC LIMIT 1"
        cursor = conn.execute(query, tuple(params))
        row = cursor.fetchone()
        if row is None:
            return None
        raw_payload = row["request_json"]
        if not raw_payload:
            return None
        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError:
            return None
        return {"task_id": row["id"], "user_id": row["user_id"], "payload": payload}
    finally:
        conn.close()


def update_task_request(
    run_id: str,
    tasks: Sequence[Dict[str, Any]],
    request_payload: Dict[str, Any],
) -> None:
    """Persist an updated request payload for ``run_id``."""

    conn = _connect()
    try:
        ensure_task_tables(conn)
        cursor = conn.execute(
            "SELECT reports_root, created_at FROM task_runs WHERE id = ?",
            (run_id,),
        )
        row = cursor.fetchone()
        if row is None:
            raise ValueError(f"Unknown task run identifier: {run_id}")

        reports_root = row["reports_root"] or "./reports"
        created_at = row["created_at"]
        now = dt.datetime.utcnow().isoformat()
        request_json = json.dumps(request_payload)
        reports_root_norm = _normalise_path(reports_root)

        conn.execute(
            """
            UPDATE task_runs
               SET request_json = ?,
                   updated_at = ?
             WHERE id = ?
            """,
            (request_json, now, run_id),
        )

        conn.execute("DELETE FROM task_entries WHERE run_id = ?", (run_id,))

        for task in tasks:
            name = task.get("name") or "unnamed"
            details = task.get("details")
            scope = task.get("scope")
            reports_path = _normalise_path(os.path.join(reports_root_norm, name, run_id))
            conn.execute(
                """
                INSERT INTO task_entries (
                    run_id, name, details, scope, reports_path, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, name, details, scope, reports_path, created_at, now),
            )

        conn.commit()
    finally:
        conn.close()


def list_task_runs_for_user(user_id: Optional[str]) -> Iterable[Dict[str, Any]]:
    """Yield task run identifiers and statuses for ``user_id``."""

    conn = _connect()
    try:
        ensure_task_tables(conn)
        if user_id is None:
            cursor = conn.execute(
                (
                    "SELECT id, user_id, status, created_at, updated_at "
                    "FROM task_runs ORDER BY created_at DESC"
                )
            )
        else:
            cursor = conn.execute(
                """
                SELECT id, user_id, status, created_at, updated_at
                  FROM task_runs
                 WHERE user_id = ?
              ORDER BY created_at DESC
                """,
                (user_id,),
            )

        for row in cursor:
            yield {
                "id": row["id"],
                "user_id": row["user_id"],
                "status": row["status"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
    finally:
        conn.close()


def store_codegen_result(
    user_id: str,
    *,
    task_name: Optional[str],
    task_index: int,
    model: Optional[str],
    code: str,
    function_name: Optional[str],
    summary_path: Optional[str] = None,
    summary_json: Optional[Dict[str, Any]] = None,
) -> int:
    """Persist a generated code snippet and return its identifier."""

    now = dt.datetime.utcnow().isoformat()
    summary_path_norm = _normalise_path(summary_path) if summary_path else None
    summary_json_text = json.dumps(summary_json) if summary_json is not None else None

    conn = _connect()
    try:
        ensure_task_tables(conn)
        cursor = conn.execute(
            """
            INSERT INTO codegen_history (
                user_id, task_name, task_index, model, code, function_name,
                summary_path, summary_json, success_count, failure_count,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                task_name,
                task_index,
                model,
                code,
                function_name,
                summary_path_norm,
                summary_json_text,
                0,
                0,
                now,
                now,
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)
    finally:
        conn.close()


def list_codegen_results(user_id: Optional[str]) -> List[Dict[str, Any]]:
    """Return stored code generation entries for ``user_id``."""

    conn = _connect()
    try:
        ensure_task_tables(conn)
        if user_id is None:
            cursor = conn.execute(
                """
                SELECT id, user_id, task_name, task_index, model, function_name,
                       summary_path, success_count, failure_count, created_at,
                       updated_at
                  FROM codegen_history
              ORDER BY updated_at DESC
                """
            )
        else:
            cursor = conn.execute(
                """
                SELECT id, user_id, task_name, task_index, model, function_name,
                       summary_path, success_count, failure_count, created_at,
                       updated_at
                  FROM codegen_history
                 WHERE user_id = ?
              ORDER BY updated_at DESC
                """,
                (user_id,),
            )

        results: List[Dict[str, Any]] = []
        for row in cursor:
            results.append(
                {
                    "id": int(row["id"]),
                    "user_id": row["user_id"],
                    "task_name": row["task_name"],
                    "task_index": row["task_index"],
                    "model": row["model"],
                    "function_name": row["function_name"],
                    "summary_path": row["summary_path"],
                    "success_count": int(row["success_count"] or 0),
                    "failure_count": int(row["failure_count"] or 0),
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
            )
        return results
    finally:
        conn.close()


def store_code_example(example: "Example", *, code_hash: str) -> None:
    """Persist ``example`` in the datastore if not already present."""

    conn = _connect()
    try:
        ensure_example_tables(conn)
        cursor = conn.execute(
            "SELECT example_id FROM code_examples WHERE code_hash = ?",
            (code_hash,),
        )
        row = cursor.fetchone()
        payload = (
            example.task_hash,
            example.language,
            example.framework,
            example.code,
            example.summary,
            json.dumps(example.metrics or {}),
            float(example.score),
            example.created_at.isoformat(),
            json.dumps(example.tags or []),
            json.dumps(example.embedding) if example.embedding is not None else None,
        )
        if row:
            existing_id = row["example_id"]
            conn.execute(
                """
                UPDATE code_examples
                   SET task_hash = ?,
                       language = ?,
                       framework = ?,
                       code = ?,
                       summary = ?,
                       metrics_json = ?,
                       score = ?,
                       created_at = ?,
                       tags_json = ?,
                       embedding_json = ?
                 WHERE example_id = ?
                """,
                (*payload, existing_id),
            )
            example.example_id = existing_id
        else:
            conn.execute(
                """
                INSERT INTO code_examples (
                    example_id, task_hash, language, framework, code, summary,
                    metrics_json, score, created_at, tags_json, embedding_json, code_hash
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    example.example_id,
                    *payload,
                    code_hash,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def load_code_examples(
    language: str, framework: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Return stored examples for ``language`` and ``framework``."""

    conn = _connect()
    try:
        ensure_example_tables(conn)
        params: List[Any] = [language]
        query = (
            """
            SELECT example_id, task_hash, language, framework, code, summary,
                   metrics_json, score, created_at, tags_json, embedding_json
              FROM code_examples
             WHERE language = ?
            """
        )
        if framework:
            query += " AND (framework IS NULL OR framework = ?)"
            params.append(framework)

        cursor = conn.execute(query, params)
        records: List[Dict[str, Any]] = []
        for row in cursor:
            metrics = json.loads(row["metrics_json"]) if row["metrics_json"] else {}
            tags = json.loads(row["tags_json"]) if row["tags_json"] else []
            embedding = (
                json.loads(row["embedding_json"]) if row["embedding_json"] else None
            )
            records.append(
                {
                    "example_id": row["example_id"],
                    "task_hash": row["task_hash"],
                    "language": row["language"],
                    "framework": row["framework"],
                    "code": row["code"],
                    "summary": row["summary"],
                    "metrics": metrics,
                    "score": row["score"],
                    "created_at": row["created_at"],
                    "tags": tags,
                    "embedding": embedding,
                }
            )
        return records
    finally:
        conn.close()


def load_codegen_result(record_id: int) -> Optional[Dict[str, Any]]:
    """Return the stored code generation record identified by ``record_id``."""

    conn = _connect()
    try:
        ensure_task_tables(conn)
        cursor = conn.execute(
            """
            SELECT id, user_id, task_name, task_index, model, code, function_name,
                   summary_path, summary_json, success_count, failure_count,
                   created_at, updated_at
              FROM codegen_history
             WHERE id = ?
            """,
            (record_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None

        summary_json = (
            json.loads(row["summary_json"])
            if row["summary_json"]
            else None
        )
        return {
            "id": int(row["id"]),
            "user_id": row["user_id"],
            "task_name": row["task_name"],
            "task_index": row["task_index"],
            "model": row["model"],
            "code": row["code"],
            "function_name": row["function_name"],
            "summary_path": row["summary_path"],
            "summary_json": summary_json,
            "success_count": int(row["success_count"] or 0),
            "failure_count": int(row["failure_count"] or 0),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
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


def record_codegen_execution(record_id: int, success: bool) -> None:
    """Increment execution counters for ``record_id`` based on ``success``."""

    column = "success_count" if success else "failure_count"
    now = dt.datetime.utcnow().isoformat()

    conn = _connect()
    try:
        ensure_task_tables(conn)
        conn.execute(
            f"""
            UPDATE codegen_history
               SET {column} = COALESCE({column}, 0) + 1,
                   updated_at = ?
             WHERE id = ?
            """,
            (now, record_id),
        )
        conn.commit()
    finally:
        conn.close()


def delete_codegen_result(record_id: int) -> None:
    """Remove the stored code generation result identified by ``record_id``."""

    conn = _connect()
    try:
        ensure_task_tables(conn)
        conn.execute("DELETE FROM codegen_history WHERE id = ?", (record_id,))
        conn.commit()
    finally:
        conn.close()
