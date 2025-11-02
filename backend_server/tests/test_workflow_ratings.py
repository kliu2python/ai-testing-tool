"""Tests covering workflow persistence and rating storage."""

from __future__ import annotations

import importlib
import sqlite3

import pytest

from backend_server.agents.data_models import (
    CustomerIssue,
    TestOutcome,
    TestStatus,
    WorkflowResult,
    WorkflowStatus,
)


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "auth.db"
    monkeypatch.setenv("AITOOL_DB_PATH", str(db_path))

    from backend_server import workflow_store as store
    from backend_server import ratings as ratings_mod

    importlib.reload(store)
    importlib.reload(ratings_mod)

    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT,
                password_hash TEXT,
                salt TEXT,
                role TEXT
            );
            INSERT OR IGNORE INTO users (id, email, password_hash, salt, role)
            VALUES ('user-1', 'owner@example.com', '', '', 'user');
            """
        )
        store.ensure_workflow_tables(conn)  # type: ignore[attr-defined]
        ratings_mod.ensure_rating_tables(conn)  # type: ignore[attr-defined]
        conn.commit()

    yield store, ratings_mod


def _sample_result() -> WorkflowResult:
    issue = CustomerIssue(
        customer_email="customer@example.com",
        subject="Crash on login",
        body="App crashes",
        platform="ios",
        os_version="17.4",
        app_version="5.2",
        steps=["Open app", "Log in"],
        expected_result="Login succeeds",
        actual_result="App crashes",
    )
    outcome = TestOutcome(status=TestStatus.PASSED, details="Reproduced successfully", report_path="/tmp/report")
    return WorkflowResult(
        status=WorkflowStatus.RESOLVED,
        issue=issue,
        outcome=outcome,
        follow_up_email=None,
        resolution_email="Resolution email",
        report="QA report",
        actions=["passed"],
        mantis_ticket=None,
    )


def test_workflow_and_rating_storage(isolated_db) -> None:
    store, ratings_mod = isolated_db

    result = _sample_result()
    stored = store.record_workflow_result(user_id="user-1", result=result, customer_email=result.issue.customer_email)

    listed = store.list_workflow_runs(owner_id="user-1")
    assert listed and listed[0].id == stored.id

    loaded = store.load_workflow_run(stored.id)
    assert loaded is not None
    assert loaded.report == "QA report"

    metrics = store.workflow_metrics("user-1")
    assert metrics["workflow_status"][WorkflowStatus.RESOLVED.value] == 1
    assert metrics["test_status"][TestStatus.PASSED.value] == 1

    record = ratings_mod.create_rating(
        "user-1",
        ratings_mod.RatingInput(
            workflow_id=stored.id,
            artifact_type=ratings_mod.ArtifactType.QA_REPORT,
            content="Excellent report",
            rating=5,
        ),
    )
    assert record.rating == 5

    averages = ratings_mod.rating_averages("user-1")
    assert pytest.approx(averages[ratings_mod.ArtifactType.QA_REPORT.value]) == 5.0

    top_examples = ratings_mod.top_rated_examples(ratings_mod.ArtifactType.QA_REPORT)
    assert top_examples == ["Excellent report"]
