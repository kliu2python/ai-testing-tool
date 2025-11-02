"""Subscription management for the multi-agent workflow portal."""

from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional

from cryptography.fernet import Fernet, InvalidToken


_PACKAGE_ROOT = Path(__file__).resolve().parent
_DB_PATH = Path(os.getenv("AITOOL_DB_PATH", str(_PACKAGE_ROOT / "auth.db")))
_FERNET_ENV = "SUBSCRIPTION_SECRET_KEY"


class SubscriptionError(RuntimeError):
    """Raised when subscription persistence fails."""


@dataclass
class SubscriptionInput:
    """Payload used when creating or updating a subscription."""

    mailbox_email: str
    imap_host: str
    imap_username: str
    imap_password: Optional[str]
    mailbox: str = "INBOX"
    use_ssl: bool = True
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    subject_keywords: List[str] = field(default_factory=list)
    enabled_functions: List[str] = field(default_factory=list)


@dataclass
class Subscription:
    """Public subscription metadata returned by the API."""

    id: str
    user_id: str
    mailbox_email: str
    imap_host: str
    imap_username: str
    mailbox: str
    use_ssl: bool
    smtp_host: Optional[str]
    smtp_port: Optional[int]
    subject_keywords: List[str]
    enabled_functions: List[str]
    created_at: dt.datetime
    updated_at: dt.datetime


@dataclass
class SubscriptionCredentials:
    """Decrypted credentials for executing a subscription run."""

    subscription: Subscription
    imap_password: str


def ensure_subscription_tables(conn: sqlite3.Connection) -> None:
    """Create the tables required for subscription storage."""

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS subscriptions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            mailbox_email TEXT NOT NULL,
            imap_host TEXT NOT NULL,
            imap_username TEXT NOT NULL,
            imap_password BLOB NOT NULL,
            mailbox TEXT NOT NULL,
            use_ssl INTEGER NOT NULL,
            smtp_host TEXT,
            smtp_port INTEGER,
            subject_keywords TEXT NOT NULL,
            enabled_functions TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """
    )


def create_subscription(user_id: str, payload: SubscriptionInput) -> Subscription:
    """Persist a new subscription for ``user_id``."""

    subscription_id = uuid.uuid4().hex
    now = dt.datetime.utcnow().isoformat()

    encrypted_password = _encrypt_secret(payload.imap_password)

    conn = sqlite3.connect(_DB_PATH)
    try:
        conn.execute(
            (
                "INSERT INTO subscriptions (id, user_id, mailbox_email, imap_host, imap_username, "
                "imap_password, mailbox, use_ssl, smtp_host, smtp_port, subject_keywords, enabled_functions, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            ),
            (
                subscription_id,
                user_id,
                payload.mailbox_email,
                payload.imap_host,
                payload.imap_username,
                encrypted_password,
                payload.mailbox,
                1 if payload.use_ssl else 0,
                payload.smtp_host,
                payload.smtp_port,
                json.dumps(payload.subject_keywords or []),
                json.dumps(_normalise_functions(payload.enabled_functions)),
                now,
                now,
            ),
        )
        conn.commit()
    except sqlite3.Error as exc:  # pragma: no cover - rare operational failure
        raise SubscriptionError(f"Failed to create subscription: {exc}") from exc
    finally:
        conn.close()

    return Subscription(
        id=subscription_id,
        user_id=user_id,
        mailbox_email=payload.mailbox_email,
        imap_host=payload.imap_host,
        imap_username=payload.imap_username,
        mailbox=payload.mailbox,
        use_ssl=payload.use_ssl,
        smtp_host=payload.smtp_host,
        smtp_port=payload.smtp_port,
        subject_keywords=payload.subject_keywords or [],
        enabled_functions=_normalise_functions(payload.enabled_functions),
        created_at=dt.datetime.fromisoformat(now),
        updated_at=dt.datetime.fromisoformat(now),
    )


def update_subscription(user_id: str, subscription_id: str, payload: SubscriptionInput) -> Subscription:
    """Update an existing subscription owned by ``user_id``."""

    updates = {
        "mailbox_email": payload.mailbox_email,
        "imap_host": payload.imap_host,
        "imap_username": payload.imap_username,
        "mailbox": payload.mailbox,
        "use_ssl": 1 if payload.use_ssl else 0,
        "smtp_host": payload.smtp_host,
        "smtp_port": payload.smtp_port,
        "subject_keywords": json.dumps(payload.subject_keywords or []),
        "enabled_functions": json.dumps(_normalise_functions(payload.enabled_functions)),
        "updated_at": dt.datetime.utcnow().isoformat(),
    }

    if payload.imap_password:
        updates["imap_password"] = _encrypt_secret(payload.imap_password)

    set_clause = ", ".join(f"{column} = ?" for column in updates)
    params = list(updates.values()) + [subscription_id, user_id]

    conn = sqlite3.connect(_DB_PATH)
    try:
        cursor = conn.execute(
            f"UPDATE subscriptions SET {set_clause} WHERE id = ? AND user_id = ?",
            params,
        )
        if cursor.rowcount == 0:
            raise SubscriptionError("Subscription not found or access denied")
        conn.commit()
    except sqlite3.Error as exc:  # pragma: no cover - operational failure
        raise SubscriptionError(f"Failed to update subscription: {exc}") from exc
    finally:
        conn.close()

    return load_subscription(user_id, subscription_id)


def delete_subscription(user_id: str, subscription_id: str) -> None:
    """Remove the subscription identified by ``subscription_id``."""

    conn = sqlite3.connect(_DB_PATH)
    try:
        cursor = conn.execute(
            "DELETE FROM subscriptions WHERE id = ? AND user_id = ?",
            (subscription_id, user_id),
        )
        if cursor.rowcount == 0:
            raise SubscriptionError("Subscription not found or access denied")
        conn.commit()
    except sqlite3.Error as exc:  # pragma: no cover - operational failure
        raise SubscriptionError(f"Failed to delete subscription: {exc}") from exc
    finally:
        conn.close()


def list_subscriptions(user_id: str) -> List[Subscription]:
    """Return all subscriptions belonging to ``user_id``."""

    conn = sqlite3.connect(_DB_PATH)
    try:
        cursor = conn.execute(
            """
            SELECT id, mailbox_email, imap_host, imap_username, mailbox, use_ssl,
                   smtp_host, smtp_port, subject_keywords, enabled_functions,
                   created_at, updated_at
            FROM subscriptions
            WHERE user_id = ?
            ORDER BY datetime(created_at) DESC
            """,
            (user_id,),
        )
        rows = cursor.fetchall()
    finally:
        conn.close()

    return [_row_to_subscription(user_id, row) for row in rows]


def load_subscription(user_id: str, subscription_id: str) -> Subscription:
    """Fetch a single subscription owned by ``user_id``."""

    conn = sqlite3.connect(_DB_PATH)
    try:
        cursor = conn.execute(
            """
            SELECT id, mailbox_email, imap_host, imap_username, mailbox, use_ssl,
                   smtp_host, smtp_port, subject_keywords, enabled_functions,
                   created_at, updated_at
            FROM subscriptions
            WHERE id = ? AND user_id = ?
            """,
            (subscription_id, user_id),
        )
        row = cursor.fetchone()
    finally:
        conn.close()

    if not row:
        raise SubscriptionError("Subscription not found or access denied")

    return _row_to_subscription(user_id, row)


def load_credentials(user_id: str, subscription_id: str) -> SubscriptionCredentials:
    """Return decrypted credentials for the requested subscription."""

    conn = sqlite3.connect(_DB_PATH)
    try:
        cursor = conn.execute(
            """
            SELECT id, mailbox_email, imap_host, imap_username, mailbox, use_ssl,
                   smtp_host, smtp_port, subject_keywords, enabled_functions,
                   created_at, updated_at, imap_password
            FROM subscriptions
            WHERE id = ? AND user_id = ?
            """,
            (subscription_id, user_id),
        )
        row = cursor.fetchone()
    finally:
        conn.close()

    if not row:
        raise SubscriptionError("Subscription not found or access denied")

    subscription = _row_to_subscription(user_id, row[:-1])
    encrypted = row[-1]
    password = _decrypt_secret(encrypted)
    return SubscriptionCredentials(subscription=subscription, imap_password=password)


def _row_to_subscription(user_id: str, row: Iterable) -> Subscription:
    (
        subscription_id,
        mailbox_email,
        imap_host,
        imap_username,
        mailbox,
        use_ssl,
        smtp_host,
        smtp_port,
        subject_keywords,
        enabled_functions,
        created_at,
        updated_at,
    ) = row

    return Subscription(
        id=subscription_id,
        user_id=user_id,
        mailbox_email=mailbox_email,
        imap_host=imap_host,
        imap_username=imap_username,
        mailbox=mailbox,
        use_ssl=bool(use_ssl),
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        subject_keywords=json.loads(subject_keywords or "[]"),
        enabled_functions=json.loads(enabled_functions or "[]"),
        created_at=dt.datetime.fromisoformat(created_at),
        updated_at=dt.datetime.fromisoformat(updated_at),
    )


def _normalise_functions(functions: Optional[Iterable[str]]) -> List[str]:
    if not functions:
        return []
    seen = []
    for value in functions:
        if value not in seen:
            seen.append(value)
    return seen


def _fernet() -> Fernet:
    secret = os.getenv(_FERNET_ENV)
    if not secret:
        raise SubscriptionError(
            "SUBSCRIPTION_SECRET_KEY environment variable is required to store IMAP credentials securely."
        )
    try:
        return Fernet(secret.encode())
    except ValueError as exc:  # pragma: no cover - misconfigured key
        raise SubscriptionError("Invalid SUBSCRIPTION_SECRET_KEY provided") from exc


def _encrypt_secret(secret: Optional[str]) -> bytes:
    if secret is None:
        raise SubscriptionError("IMAP password is required")
    fernet = _fernet()
    return fernet.encrypt(secret.encode("utf-8"))


def _decrypt_secret(token: bytes) -> str:
    fernet = _fernet()
    try:
        return fernet.decrypt(token).decode("utf-8")
    except InvalidToken as exc:  # pragma: no cover - indicates tampering
        raise SubscriptionError("Failed to decrypt stored credentials") from exc

