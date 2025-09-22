"""Background worker that consumes the Redis task queue."""

from __future__ import annotations

import json
import signal
from typing import Any, Dict, Optional

from redis import RedisError

from runner import _run_tasks
from task_queue import (
    create_redis_client,
    dump_status,
    queue_key,
    status_key,
)


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
    _update_status(redis_client, task_id, {"status": "running"}, owner_id)

    try:
        result = _run_tasks(
            task["prompt"],
            task["tasks"],
            task["server"],
            task["platform"],
            task["reports_folder"],
            task["debug"],
        )
    except Exception as exc:  # pragma: no cover - background safety net
        _update_status(
            redis_client,
            task_id,
            {"status": "failed", "error": str(exc)},
            owner_id,
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
        print("Shutting down queue runner")
    except RedisError as exc:  # pragma: no cover - operational errors
        print(f"[ERROR] Redis interaction failed: {exc}")
    finally:
        redis_client.close()


if __name__ == "__main__":
    main()
