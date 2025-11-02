"""Tests for subscription storage helpers."""

from __future__ import annotations

import importlib
import sqlite3

import pytest

try:
    from cryptography.fernet import Fernet
except ImportError:  # pragma: no cover - dependency optional in minimal envs
    pytest.skip("cryptography package is required for subscription tests", allow_module_level=True)


def test_create_and_load_subscription(tmp_path, monkeypatch) -> None:
    key = Fernet.generate_key().decode()
    db_path = tmp_path / "auth.db"

    monkeypatch.setenv("SUBSCRIPTION_SECRET_KEY", key)
    monkeypatch.setenv("AITOOL_DB_PATH", str(db_path))

    from backend_server import subscriptions as subs

    importlib.reload(subs)

    with sqlite3.connect(subs._DB_PATH) as conn:  # type: ignore[attr-defined]
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT,
                password_hash TEXT,
                salt TEXT,
                role TEXT
            );
            """
        )
        subs.ensure_subscription_tables(conn)
        conn.execute(
            "INSERT OR IGNORE INTO users (id, email, password_hash, salt, role) VALUES (?, ?, '', '', 'user')",
            ("user-1", "tester@example.com"),
        )
        conn.commit()

    payload = subs.SubscriptionInput(
        mailbox_email="support@example.com",
        imap_host="imap.example.com",
        imap_username="support@example.com",
        imap_password="app-password",
        subject_keywords=["crash"],
        enabled_functions=["auto_test", "create_mantis_ticket"],
    )

    created = subs.create_subscription("user-1", payload)
    assert created.id
    assert created.mailbox_email == "support@example.com"

    listed = subs.list_subscriptions("user-1")
    assert len(listed) == 1
    assert listed[0].enabled_functions == ["auto_test", "create_mantis_ticket"]

    creds = subs.load_credentials("user-1", created.id)
    assert creds.imap_password == "app-password"

    updated_payload = subs.SubscriptionInput(
        mailbox_email="support@example.com",
        imap_host="imap.example.com",
        imap_username="support@example.com",
        imap_password="new-password",
        subject_keywords=["timeout"],
        enabled_functions=["request_additional_details"],
    )

    updated = subs.update_subscription("user-1", created.id, updated_payload)
    assert updated.subject_keywords == ["timeout"]
    assert updated.enabled_functions == ["request_additional_details"]

    creds_after_update = subs.load_credentials("user-1", created.id)
    assert creds_after_update.imap_password == "new-password"

    subs.delete_subscription("user-1", created.id)
    assert subs.list_subscriptions("user-1") == []
