"""Tests for example scoring utilities."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend_server.example_bootstrap import (
    ExampleConfig,
    load_example_config,
    score_human,
    score_metrics,
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
