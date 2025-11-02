"""Rating storage and style guidance helpers for AI generated content."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import sqlite3
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional


_PACKAGE_ROOT = Path(__file__).resolve().parent
_DB_PATH = Path(os.getenv("AITOOL_DB_PATH", str(_PACKAGE_ROOT / "auth.db")))


class ArtifactType(str, Enum):
    """Content categories that can be rated by humans."""

    FOLLOW_UP_EMAIL = "follow_up_email"
    RESOLUTION_EMAIL = "resolution_email"
    QA_REPORT = "qa_report"
    MANTIS_TICKET = "mantis_ticket"


@dataclass
class RatingInput:
    """Payload accepted when creating a rating."""

    workflow_id: str
    artifact_type: ArtifactType
    content: str
    rating: int
    notes: Optional[str] = None


@dataclass
class RatingRecord:
    """Structured representation of a stored rating."""

    id: str
    workflow_id: str
    user_id: str
    artifact_type: ArtifactType
    content: str
    content_hash: str
    rating: int
    notes: Optional[str]
    created_at: dt.datetime
    updated_at: dt.datetime


def ensure_rating_tables(conn: sqlite3.Connection) -> None:
    """Create the ratings table when absent."""

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS workflow_ratings (
            id TEXT PRIMARY KEY,
            workflow_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            artifact_type TEXT NOT NULL,
            content TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            rating INTEGER NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(workflow_id) REFERENCES workflow_runs(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_ratings_artifact_hash
            ON workflow_ratings(artifact_type, content_hash);
        """
    )


def create_rating(user_id: str, payload: RatingInput) -> RatingRecord:
    """Store a human rating for generated content."""

    if payload.rating < 1 or payload.rating > 5:
        raise ValueError("rating must be between 1 and 5")

    rating_id = uuid.uuid4().hex
    now = dt.datetime.utcnow().isoformat()
    content_hash = hashlib.sha256(payload.content.encode("utf-8")).hexdigest()

    conn = sqlite3.connect(_DB_PATH)
    try:
        ensure_rating_tables(conn)
        conn.execute(
            (
                "INSERT INTO workflow_ratings (id, workflow_id, user_id, artifact_type, content, content_hash, rating, notes, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            ),
            (
                rating_id,
                payload.workflow_id,
                user_id,
                payload.artifact_type.value,
                payload.content,
                content_hash,
                payload.rating,
                payload.notes,
                now,
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return RatingRecord(
        id=rating_id,
        workflow_id=payload.workflow_id,
        user_id=user_id,
        artifact_type=payload.artifact_type,
        content=payload.content,
        content_hash=content_hash,
        rating=payload.rating,
        notes=payload.notes,
        created_at=dt.datetime.fromisoformat(now),
        updated_at=dt.datetime.fromisoformat(now),
    )


def list_ratings(
    *,
    owner_id: Optional[str] = None,
    artifact_type: Optional[ArtifactType] = None,
    limit: int = 200,
) -> List[RatingRecord]:
    """Return stored ratings filtered by owner and artifact type."""

    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        ensure_rating_tables(conn)
        clauses = []
        params: List[object] = []
        if owner_id:
            clauses.append("user_id = ?")
            params.append(owner_id)
        if artifact_type:
            clauses.append("artifact_type = ?")
            params.append(artifact_type.value)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = (
            "SELECT * FROM workflow_ratings "
            + where
            + " ORDER BY datetime(created_at) DESC LIMIT ?"
        )
        params.append(limit)
        rows = conn.execute(query, tuple(params)).fetchall()
    finally:
        conn.close()

    results: List[RatingRecord] = []
    for row in rows:
        results.append(
            RatingRecord(
                id=row["id"],
                workflow_id=row["workflow_id"],
                user_id=row["user_id"],
                artifact_type=ArtifactType(row["artifact_type"]),
                content=row["content"],
                content_hash=row["content_hash"],
                rating=int(row["rating"]),
                notes=row["notes"],
                created_at=dt.datetime.fromisoformat(row["created_at"]),
                updated_at=dt.datetime.fromisoformat(row["updated_at"]),
            )
        )
    return results


def rating_averages(owner_id: Optional[str] = None) -> Dict[str, float]:
    """Return average rating per artifact type."""

    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        ensure_rating_tables(conn)
        if owner_id:
            rows = conn.execute(
                "SELECT artifact_type, AVG(rating) as avg_rating FROM workflow_ratings WHERE user_id = ? GROUP BY artifact_type",
                (owner_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT artifact_type, AVG(rating) as avg_rating FROM workflow_ratings GROUP BY artifact_type"
            ).fetchall()
    finally:
        conn.close()

    return {
        row["artifact_type"]: float(row["avg_rating"]) for row in rows if row["artifact_type"]
    }


def top_rated_examples(
    artifact_type: ArtifactType,
    *,
    limit: int = 3,
) -> List[str]:
    """Return the highest-rated distinct pieces of content for ``artifact_type``."""

    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        ensure_rating_tables(conn)
        rows = conn.execute(
            (
                "SELECT content, MAX(rating) as rating, MAX(updated_at) as updated_at "
                "FROM workflow_ratings WHERE artifact_type = ? "
                "GROUP BY content_hash ORDER BY rating DESC, updated_at DESC LIMIT ?"
            ),
            (artifact_type.value, limit),
        ).fetchall()
    finally:
        conn.close()

    return [row["content"] for row in rows]

