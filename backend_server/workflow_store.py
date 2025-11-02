"""Persistence helpers for orchestrated workflow runs."""

from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from backend_server.agents.data_models import TestStatus, WorkflowResult, WorkflowStatus

_PACKAGE_ROOT = Path(__file__).resolve().parent
_DB_PATH = Path(os.getenv("AITOOL_DB_PATH", str(_PACKAGE_ROOT / "auth.db")))


@dataclass
class StoredWorkflow:
    """Structured representation of a persisted workflow run."""

    id: str
    user_id: str
    subscription_id: Optional[str]
    customer_email: Optional[str]
    status: WorkflowStatus
    test_status: Optional[TestStatus]
    actions: List[str]
    follow_up_email: Optional[str]
    resolution_email: Optional[str]
    report: str
    mantis_ticket: Optional[Dict[str, object]]
    created_at: dt.datetime
    updated_at: dt.datetime


def ensure_workflow_tables(conn: sqlite3.Connection) -> None:
    """Create workflow persistence tables when absent."""

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS workflow_runs (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            subscription_id TEXT,
            customer_email TEXT,
            status TEXT NOT NULL,
            test_status TEXT,
            actions TEXT NOT NULL,
            follow_up_email TEXT,
            resolution_email TEXT,
            report TEXT NOT NULL,
            mantis_ticket TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(subscription_id) REFERENCES subscriptions(id) ON DELETE SET NULL
        );
        """
    )


def record_workflow_result(
    *,
    user_id: str,
    result: WorkflowResult,
    subscription_id: Optional[str] = None,
    customer_email: Optional[str] = None,
) -> StoredWorkflow:
    """Persist ``result`` and return the stored representation."""

    workflow_id = uuid.uuid4().hex
    now = dt.datetime.utcnow().isoformat()

    actions = json.dumps(result.actions)
    mantis_json = json.dumps(_serialise_ticket(result.mantis_ticket))
    test_status = result.outcome.status.value if result.outcome else None

    conn = sqlite3.connect(_DB_PATH)
    try:
        ensure_workflow_tables(conn)
        conn.execute(
            (
                "INSERT INTO workflow_runs (id, user_id, subscription_id, customer_email, status, "
                "test_status, actions, follow_up_email, resolution_email, report, mantis_ticket, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            ),
            (
                workflow_id,
                user_id,
                subscription_id,
                customer_email,
                result.status.value,
                test_status,
                actions,
                result.follow_up_email,
                result.resolution_email,
                result.report,
                mantis_json,
                now,
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return StoredWorkflow(
        id=workflow_id,
        user_id=user_id,
        subscription_id=subscription_id,
        customer_email=customer_email,
        status=result.status,
        test_status=result.outcome.status if result.outcome else None,
        actions=list(result.actions),
        follow_up_email=result.follow_up_email,
        resolution_email=result.resolution_email,
        report=result.report,
        mantis_ticket=_serialise_ticket(result.mantis_ticket),
        created_at=dt.datetime.fromisoformat(now),
        updated_at=dt.datetime.fromisoformat(now),
    )


def _serialise_ticket(ticket: Optional[Dict[str, object] | object]) -> Optional[Dict[str, object]]:
    if ticket is None:
        return None
    if isinstance(ticket, dict):
        return ticket
    if hasattr(ticket, "__dict__"):
        return {key: value for key, value in vars(ticket).items() if not key.startswith("_")}
    return None


def list_workflow_runs(
    *,
    owner_id: Optional[str] = None,
    limit: int = 100,
) -> List[StoredWorkflow]:
    """Return workflow runs filtered by ``owner_id``."""

    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        ensure_workflow_tables(conn)
        query = "SELECT * FROM workflow_runs"
        params: Iterable[object]
        if owner_id:
            query += " WHERE user_id = ?"
            params = (owner_id,)
        else:
            params = ()
        query += " ORDER BY datetime(created_at) DESC LIMIT ?"
        params = tuple(params) + (limit,)
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()

    results: List[StoredWorkflow] = []
    for row in rows:
        results.append(
            StoredWorkflow(
                id=row["id"],
                user_id=row["user_id"],
                subscription_id=row["subscription_id"],
                customer_email=row["customer_email"],
                status=WorkflowStatus(row["status"]),
                test_status=TestStatus(row["test_status"]) if row["test_status"] else None,
                actions=json.loads(row["actions"] or "[]"),
                follow_up_email=row["follow_up_email"],
                resolution_email=row["resolution_email"],
                report=row["report"],
                mantis_ticket=json.loads(row["mantis_ticket"]) if row["mantis_ticket"] else None,
                created_at=dt.datetime.fromisoformat(row["created_at"]),
                updated_at=dt.datetime.fromisoformat(row["updated_at"]),
            )
        )
    return results


def load_workflow_run(workflow_id: str) -> Optional[StoredWorkflow]:
    """Return a single workflow run identified by ``workflow_id``."""

    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        ensure_workflow_tables(conn)
        row = conn.execute(
            "SELECT * FROM workflow_runs WHERE id = ?",
            (workflow_id,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None

    return StoredWorkflow(
        id=row["id"],
        user_id=row["user_id"],
        subscription_id=row["subscription_id"],
        customer_email=row["customer_email"],
        status=WorkflowStatus(row["status"]),
        test_status=TestStatus(row["test_status"]) if row["test_status"] else None,
        actions=json.loads(row["actions"] or "[]"),
        follow_up_email=row["follow_up_email"],
        resolution_email=row["resolution_email"],
        report=row["report"],
        mantis_ticket=json.loads(row["mantis_ticket"]) if row["mantis_ticket"] else None,
        created_at=dt.datetime.fromisoformat(row["created_at"]),
        updated_at=dt.datetime.fromisoformat(row["updated_at"]),
    )


def workflow_metrics(owner_id: Optional[str] = None) -> Dict[str, Dict[str, int]]:
    """Return aggregated workflow metrics for dashboards."""

    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        ensure_workflow_tables(conn)
        if owner_id:
            status_rows = conn.execute(
                "SELECT status, COUNT(*) as count FROM workflow_runs WHERE user_id = ? GROUP BY status",
                (owner_id,),
            ).fetchall()
            test_rows = conn.execute(
                "SELECT test_status, COUNT(*) as count FROM workflow_runs WHERE user_id = ? GROUP BY test_status",
                (owner_id,),
            ).fetchall()
        else:
            status_rows = conn.execute(
                "SELECT status, COUNT(*) as count FROM workflow_runs GROUP BY status"
            ).fetchall()
            test_rows = conn.execute(
                "SELECT test_status, COUNT(*) as count FROM workflow_runs GROUP BY test_status"
            ).fetchall()
    finally:
        conn.close()

    status_counts = {row["status"]: int(row["count"]) for row in status_rows if row["status"]}
    test_counts = {row["test_status"]: int(row["count"]) for row in test_rows if row["test_status"]}
    return {"workflow_status": status_counts, "test_status": test_counts}

