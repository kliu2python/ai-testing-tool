"""Example persistence and prompt bootstrapping utilities."""

from __future__ import annotations

import datetime as dt
import json
import logging
import math
import os
import re
import sqlite3
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Dict, Iterable, List, Optional
from uuid import uuid4

from backend_server.task_store import load_code_examples, store_code_example


logger = logging.getLogger(__name__)


_DEFAULT_SCORING_WEIGHTS: Dict[str, float] = {
    "tests_passed": 1.0,
    "human_score": 0.8,
    "lint_errors": -0.5,
    "token_usage": -0.2,
    "compile_success": 0.3,
    "runtime_seconds": -0.1,
}

_SECRET_PATTERN = re.compile(
    r"(?i)(api[_-]?key|token|secret|password|client[_-]?id)\s*[:=]\s*['\"]?[A-Za-z0-9-_]{8,}['\"]?"
)


def _bool_from_env(env_name: str, default: bool) -> bool:
    value = os.getenv(env_name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _json_from_env(env_name: str) -> Optional[Dict[str, float]]:
    raw = os.getenv(env_name)
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Failed to parse JSON from %s", env_name)
        return None
    if not isinstance(parsed, dict):
        logger.warning("Expected object JSON for %s, received %s", env_name, type(parsed))
        return None
    numeric: Dict[str, float] = {}
    for key, value in parsed.items():
        try:
            numeric[key] = float(value)
        except (TypeError, ValueError):
            logger.debug("Ignoring non-numeric weight %s=%s from %s", key, value, env_name)
    return numeric


@dataclass
class ExampleConfig:
    """Runtime configuration for example bootstrapping."""

    enable_example_bootstrap: bool = True
    example_token_budget: int = 1200
    freshness_half_life_days: float = 14.0
    similarity_threshold: float = 0.92
    scoring_weights: Dict[str, float] = field(default_factory=lambda: dict(_DEFAULT_SCORING_WEIGHTS))


def load_example_config() -> ExampleConfig:
    """Return configuration derived from environment variables."""

    config = ExampleConfig()
    config.enable_example_bootstrap = _bool_from_env("ENABLE_EXAMPLE_BOOTSTRAP", True)

    budget = os.getenv("EXAMPLE_TOKEN_BUDGET")
    if budget:
        try:
            config.example_token_budget = max(int(budget), 0)
        except ValueError:
            logger.warning("Invalid EXAMPLE_TOKEN_BUDGET value '%s'", budget)

    half_life = os.getenv("EXAMPLE_FRESHNESS_HALF_LIFE_DAYS")
    if half_life:
        try:
            config.freshness_half_life_days = max(float(half_life), 0.01)
        except ValueError:
            logger.warning(
                "Invalid EXAMPLE_FRESHNESS_HALF_LIFE_DAYS value '%s'", half_life
            )

    threshold = os.getenv("EXAMPLE_SIMILARITY_THRESHOLD")
    if threshold:
        try:
            config.similarity_threshold = float(threshold)
        except ValueError:
            logger.warning("Invalid EXAMPLE_SIMILARITY_THRESHOLD '%s'", threshold)

    weights = _json_from_env("EXAMPLE_SCORING_WEIGHTS")
    if weights:
        config.scoring_weights.update(weights)

    return config


@dataclass
class GenerationTask:
    """Description of the current generation request."""

    instruction: str
    context: str
    language: str
    framework: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    task_hash: Optional[str] = None
    embedding: Optional[List[float]] = None

    def ensure_hash(self) -> str:
        if not self.task_hash:
            self.task_hash = hash_task(self.instruction, self.context)
        return self.task_hash

    def ensure_embedding(self, config: ExampleConfig) -> Optional[List[float]]:
        if not config.enable_example_bootstrap:
            return None
        if self.embedding is None:
            self.embedding = embed_text(f"{self.instruction}\n{self.context}")
        return self.embedding

    def normalised_tags(self) -> List[str]:
        return sorted({tag for tag in self.tags if tag})


@dataclass
class Example:
    """Stored example metadata used for in-context bootstrapping."""

    example_id: str
    task_hash: str
    language: str
    framework: Optional[str]
    code: str
    summary: str
    metrics: Dict[str, float]
    score: float
    created_at: dt.datetime
    tags: List[str]
    embedding: Optional[List[float]] = None

    rank_score: float = 0.0


def hash_task(instruction: str, context: str) -> str:
    """Create a deterministic hash for the supplied task description."""

    payload = f"{instruction}\n\n{context}".encode("utf-8")
    return sha256(payload).hexdigest()


def sanitize_text(value: str) -> str:
    """Redact obvious secret patterns from ``value``."""

    return _SECRET_PATTERN.sub("[REDACTED]", value or "")


def normalise_code(code: str) -> str:
    """Return a normalised representation of ``code`` for hashing."""

    return re.sub(r"\s+", "", code or "").strip()


def summarize_code(code: str, max_length: int = 200) -> str:
    """Return a compact summary derived from ``code``."""

    lines = [line.strip() for line in (code or "").splitlines() if line.strip()]
    if not lines:
        return "Empty code sample."
    summary: List[str] = []
    for line in lines:
        summary.append(line)
        if len(" ".join(summary)) >= max_length:
            break
    joined = " ".join(summary)
    if len(joined) > max_length:
        return f"{joined[: max_length - 3]}..."
    return joined


def score_metrics(metrics: Dict[str, float], weights: Dict[str, float]) -> float:
    """Compute a weighted score for ``metrics``."""

    return sum(weights.get(key, 0.0) * float(metrics.get(key, 0.0)) for key in metrics)


def score_human(value: Optional[float]) -> float:
    """Normalise a user supplied score into the ``[-1.0, 1.0]`` range.

    The returned value is stored as-is in the metrics payload; it is weighted when
    ``score_metrics`` is invoked. Inputs that cannot be represented as floating
    point numbers are ignored and treated as neutral feedback (``0.0``).
    """

    if value is None:
        return 0.0
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        logger.debug("Ignoring invalid human score value: %s", value)
        return 0.0
    return max(min(numeric, 1.0), -1.0)


def estimate_tokens(text: str) -> int:
    """Rudimentary token estimator based on whitespace splitting."""

    if not text:
        return 0
    return max(1, len(text.split()))


def truncate_text_by_tokens(text: str, max_tokens: int) -> str:
    """Return ``text`` truncated to ``max_tokens`` tokens (approximate)."""

    if max_tokens <= 0:
        return ""
    tokens = text.split()
    if len(tokens) <= max_tokens:
        return text
    truncated = tokens[: max_tokens - 1] if max_tokens > 1 else tokens[:1]
    return " ".join(truncated) + " ..."


def embed_text(text: str, dimensions: int = 128) -> List[float]:
    """Generate a simple deterministic embedding for ``text``."""

    tokens = re.findall(r"[A-Za-z0-9_]+", (text or "").lower())
    if not tokens:
        return [0.0] * dimensions
    vector = [0.0] * dimensions
    for token in tokens:
        digest = int(sha256(token.encode("utf-8")).hexdigest(), 16)
        index = digest % dimensions
        vector[index] += 1.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def cosine_similarity(left: Iterable[float], right: Iterable[float]) -> float:
    """Return the cosine similarity between ``left`` and ``right``."""

    left_list = list(left)
    right_list = list(right)
    if len(left_list) != len(right_list) or not left_list:
        return 0.0
    numerator = sum(a * b for a, b in zip(left_list, right_list))
    left_norm = math.sqrt(sum(a * a for a in left_list)) or 1.0
    right_norm = math.sqrt(sum(b * b for b in right_list)) or 1.0
    return numerator / (left_norm * right_norm)


def record_generation_result(
    task: GenerationTask,
    code: str,
    metrics: Optional[Dict[str, float]] = None,
    human_score: Optional[float] = None,
    *,
    config: Optional[ExampleConfig] = None,
) -> Optional[Example]:
    """Persist a completed generation using ``task`` metadata."""

    cfg = config or load_example_config()
    if not cfg.enable_example_bootstrap:
        return None

    metrics = {key: float(value) for key, value in (metrics or {}).items()}
    if "human_score" in metrics:
        metrics["human_score"] = score_human(metrics["human_score"])
    elif human_score is not None:
        metrics["human_score"] = score_human(human_score)
    sanitized_code = sanitize_text(code or "")
    summary = summarize_code(sanitized_code)
    task_hash = task.ensure_hash()
    embedding = task.ensure_embedding(cfg)

    example = Example(
        example_id=str(uuid4()),
        task_hash=task_hash,
        language=task.language,
        framework=task.framework,
        code=sanitized_code,
        summary=summary,
        metrics=metrics,
        score=score_metrics(metrics, cfg.scoring_weights),
        created_at=dt.datetime.utcnow(),
        tags=task.normalised_tags(),
        embedding=embedding,
    )

    try:
        store_code_example(
            example,
            code_hash=hash_task("code", normalise_code(sanitized_code)),
        )
    except sqlite3.Error as exc:  # pragma: no cover - operational failure
        logger.warning("Failed to store example: %s", exc)
        return example

    return example


def _load_candidates(task: GenerationTask, cfg: ExampleConfig) -> List[Example]:
    records = load_code_examples(task.language, task.framework)
    candidates: List[Example] = []
    for record in records:
        timestamp = record.get("created_at")
        if not isinstance(timestamp, str):
            logger.debug("Skipping example with missing timestamp")
            continue
        try:
            created_at = dt.datetime.fromisoformat(timestamp)
        except ValueError:
            logger.debug("Skipping example with invalid timestamp %s", timestamp)
            continue
        metrics = record.get("metrics") or {}
        example = Example(
            example_id=record["example_id"],
            task_hash=record["task_hash"],
            language=record["language"],
            framework=record.get("framework"),
            code=record["code"],
            summary=record.get("summary", ""),
            metrics={key: float(value) for key, value in metrics.items()},
            score=float(record.get("score", 0.0)),
            created_at=created_at,
            tags=record.get("tags", []),
            embedding=record.get("embedding"),
        )
        candidates.append(example)
    return candidates


def select_top_examples(
    task: GenerationTask,
    *,
    config: Optional[ExampleConfig] = None,
) -> List[Example]:
    """Return up to three relevant examples for ``task``."""

    cfg = config or load_example_config()
    if not cfg.enable_example_bootstrap:
        return []

    candidates = _load_candidates(task, cfg)
    if not candidates:
        return []

    task_hash = task.ensure_hash()
    task_embedding = task.ensure_embedding(cfg)
    now = dt.datetime.utcnow()
    half_life = cfg.freshness_half_life_days or 0.01

    for candidate in candidates:
        age_days = max((now - candidate.created_at).total_seconds() / 86400.0, 0.0)
        freshness = math.exp(-age_days / half_life)
        rank = candidate.score * freshness
        if candidate.task_hash == task_hash:
            rank *= 1.05
        if task_embedding and candidate.embedding:
            similarity = cosine_similarity(task_embedding, candidate.embedding)
            candidate.rank_score = rank * (1.0 + max(similarity, 0.0))
        else:
            candidate.rank_score = rank

    candidates.sort(key=lambda item: item.rank_score, reverse=True)

    chosen: List[Example] = []
    for candidate in candidates:
        if candidate.rank_score <= 0:
            continue
        if cfg.similarity_threshold and chosen and candidate.embedding:
            too_similar = False
            for existing in chosen:
                if not existing.embedding:
                    continue
                similarity = cosine_similarity(candidate.embedding, existing.embedding)
                if similarity > cfg.similarity_threshold:
                    too_similar = True
                    break
            if too_similar:
                continue
        chosen.append(candidate)
        if len(chosen) >= 3:
            break

    return chosen


def build_examples_block(
    task: GenerationTask,
    *,
    config: Optional[ExampleConfig] = None,
) -> str:
    """Return a formatted examples block for prompt insertion."""

    cfg = config or load_example_config()
    if not cfg.enable_example_bootstrap:
        return ""

    examples = select_top_examples(task, config=cfg)
    if not examples:
        return ""

    token_budget = max(cfg.example_token_budget, 0)
    remaining_budget = token_budget
    blocks: List[str] = []
    for index, example in enumerate(examples, start=1):
        if token_budget:
            if remaining_budget <= 0:
                break
            remaining = len(examples) - index + 1
            per_example = max(1, remaining_budget // remaining) if remaining_budget else 1
            excerpt = truncate_text_by_tokens(example.code, per_example)
            consumed = min(estimate_tokens(excerpt), remaining_budget)
            remaining_budget = max(remaining_budget - consumed, 0)
        else:
            excerpt = example.code
        block = (
            f"Example {index} (score {example.score:.2f}):\n"
            f"Reasoning: {example.summary}\n"
            f"Code:\n```{task.language}\n{excerpt}\n```"
        )
        blocks.append(block)
    return "\n\n".join(blocks)


