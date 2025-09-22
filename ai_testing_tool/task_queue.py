"""Utilities for interacting with the Redis-backed task queue."""

from __future__ import annotations

import json
import os
from typing import Any, Dict

from redis import Redis
from redis.asyncio import Redis as AsyncRedis


DEFAULT_REDIS_URL = "redis://localhost:6379/0"
_QUEUE_KEY_ENV = "AITASK_QUEUE_KEY"
_STATUS_PREFIX_ENV = "AITASK_STATUS_PREFIX"


def _redis_url() -> str:
    """Return the Redis connection URL from the environment."""

    return os.getenv("REDIS_URL", DEFAULT_REDIS_URL)


def queue_key() -> str:
    """Return the Redis list key used for pending tasks."""

    return os.getenv(_QUEUE_KEY_ENV, "ai_testing_tool:queue")


def status_key(task_id: str) -> str:
    """Return the Redis key storing status for ``task_id``."""

    prefix = os.getenv(_STATUS_PREFIX_ENV, "ai_testing_tool:status:")
    return f"{prefix}{task_id}"


def create_async_redis_client() -> AsyncRedis:
    """Create an asynchronous Redis client instance."""

    return AsyncRedis.from_url(_redis_url(), decode_responses=True)


def create_redis_client() -> Redis:
    """Create a synchronous Redis client instance."""

    return Redis.from_url(_redis_url(), decode_responses=True)


def dump_status(payload: Dict[str, Any]) -> str:
    """Serialise a status payload into a JSON string."""

    return json.dumps(payload)


def load_status(raw: str) -> Dict[str, Any]:
    """Parse a stored JSON status payload from Redis."""

    return json.loads(raw)
