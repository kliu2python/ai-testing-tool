"""Background worker that consumes the Redis task queue."""

from __future__ import annotations

import json
import logging
import signal
from typing import Any, Dict, Optional

from redis import RedisError

from backend_server.logging_config import configure_logging
from backend_server.runner import _run_tasks
from backend_server.task_queue import (
    create_redis_client,
    dump_status,
    queue_key,
    status_key,
)
from backend_server.task_store import set_task_status

configure_logging()

logger = logging.getLogger(__name__)


def _update_status(
    redis_client: Any,
    task_id: str,
    payload: Dict[str, Any],
    owner_id: Optional[str],
) -> None:
    """Persist ``payload`` as the status for ``task_id``."""

    data = dict(payload)
    if owner_id is not None:
        data["user_id"] = owner_id
    redis_client.set(status_key(task_id), dump_status(data))


def _process_task(redis_client: Any, raw_task: str) -> None:
    """Execute a single queued task represented by ``raw_task``."""

    task: Dict[str, Any] = json.loads(raw_task)
    task_id = task["task_id"]
    owner_id: Optional[str] = task.get("user_id")
    base_reports_folder = task.get("reports_folder") or "./reports"
    logger.info("Starting task %s for user %s", task_id, owner_id or "<anonymous>")
    _update_status(redis_client, task_id, {"status": "running"}, owner_id)
    set_task_status(
        task_id,
        "running",
        user_id=owner_id,
        reports_root=base_reports_folder,
    )

    reports_folder = base_reports_folder

    try:
        result = _run_tasks(
            task["prompt"],
            task["tasks"],
            task["server"],
            task["platform"],
            reports_folder,
            task["debug"],
            task_id=task_id,
            llm_mode=task.get("llm_mode"),
            targets=task.get("targets"),
        )
    except Exception as exc:  # pragma: no cover - background safety net
        logger.exception("Task %s failed: %s", task_id, exc)
        _update_status(
            redis_client,
            task_id,
            {"status": "failed", "error": str(exc)},
            owner_id,
        )
        set_task_status(
            task_id,
            "failed",
            error=str(exc),
            user_id=owner_id,
            reports_root=base_reports_folder,
        )
        return

    _update_status(
        redis_client,
        task_id,
        {
            "status": "completed",
            "summary": result.summary,
            "summary_path": result.summary_path,
        },
        owner_id,
    )
    set_task_status(
        task_id,
        "completed",
        summary=result.summary,
        summary_path=result.summary_path,
        user_id=owner_id,
        reports_root=base_reports_folder,
    )
    logger.info("Completed task %s", task_id)


def main() -> None:
    """Run the blocking loop that processes queued tasks."""

    redis_client = create_redis_client()

    def _handle_shutdown(signum: int, _frame: Optional[Any]) -> None:
        raise KeyboardInterrupt

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, _handle_shutdown)

    try:
        while True:
            item = redis_client.blpop(queue_key(), timeout=5)
            if not item:
                continue
            _, raw_task = item
            _process_task(redis_client, raw_task)
    except KeyboardInterrupt:
        logger.info("Shutting down queue runner")
    except RedisError as exc:  # pragma: no cover - operational errors
        logger.error("Redis interaction failed: %s", exc)
    finally:
        redis_client.close()


if __name__ == "__main__":
    main()
