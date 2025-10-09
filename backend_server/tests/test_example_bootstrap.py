"""Tests for example scoring utilities."""

from __future__ import annotations

import sys
import datetime as dt
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend_server.example_bootstrap import (
    Example,
    ExampleConfig,
    hash_task,
    load_example_config,
    normalise_code,
    score_human,
    score_metrics,
)
from backend_server.task_store import (
    load_example_by_code_hash,
    store_code_example,
    update_example_metrics,
    ensure_example_tables,
)


def test_score_human_clamps_and_sanitises_values():
    assert score_human(None) == 0.0
    assert score_human(0.5) == 0.5
    assert score_human("0.25") == 0.25
    assert score_human(5.0) == 1.0
    assert score_human(-2.0) == -1.0


def test_score_metrics_includes_human_weight():
    config: ExampleConfig = load_example_config()
    weights = config.scoring_weights
    assert weights["tests_passed"] > weights["human_score"]

    metrics = {"tests_passed": 1.0, "human_score": 0.5}
    expected = (
        weights["tests_passed"] * metrics["tests_passed"]
        + weights["human_score"] * metrics["human_score"]
    )
    assert score_metrics(metrics, weights) == expected


def test_update_example_metrics_persists_human_feedback(tmp_path, monkeypatch):
    from backend_server import task_store

    db_path = tmp_path / "examples.db"
    monkeypatch.setattr(task_store, "_DB_PATH", db_path)

    conn = sqlite3.connect(db_path)
    try:
        ensure_example_tables(conn)
        conn.commit()
    finally:
        conn.close()

    config: ExampleConfig = load_example_config()
    example = Example(
        example_id="example-1",
        task_hash="task-123",
        language="python",
        framework=None,
        code="print('hello')",
        summary="print('hello')",
        metrics={"tests_passed": 1.0},
        score=1.0,
        created_at=dt.datetime.utcnow(),
        tags=[],
    )
    code_hash = hash_task("code", normalise_code(example.code))
    store_code_example(example, code_hash=code_hash)

    stored = load_example_by_code_hash(code_hash)
    assert stored is not None
    assert stored["metrics"] == {"tests_passed": 1.0}

    metrics = dict(stored["metrics"])
    metrics["human_score"] = 0.25
    new_score = score_metrics(metrics, config.scoring_weights)
    assert update_example_metrics(code_hash, metrics, new_score)

    refreshed = load_example_by_code_hash(code_hash)
    assert refreshed is not None
    assert refreshed["metrics"]["human_score"] == 0.25
    assert refreshed["score"] == new_score
