"""Utilities for generating test code from automation summaries."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from openai import OpenAI

logger = logging.getLogger(__name__)


class CodegenError(RuntimeError):
    """Raised when code generation cannot be completed."""


@dataclass
class CodegenResult:
    """Container returned after generating code."""

    code: str
    model: str
    task_name: Optional[str] = None
    function_name: Optional[str] = None


_CODE_FENCE_PATTERN = re.compile(r"```(?:python)?\s*([\s\S]+?)\s*```", re.IGNORECASE)


def _strip_code_fences(content: str) -> str:
    """Return ``content`` without Markdown code fences when present."""

    match = _CODE_FENCE_PATTERN.search(content)
    if match:
        return match.group(1).strip()
    return content.strip()


def _slugify(value: str, fallback: str = "scenario") -> str:
    """Return a pytest-friendly slug based on ``value``."""

    if not value:
        return fallback
    slug = re.sub(r"[^0-9a-zA-Z]+", "_", value.strip().lower()).strip("_")
    return slug or fallback


def _load_summary_from_path(summary_path: str) -> Dict[str, Any]:
    """Load a JSON summary from ``summary_path``."""

    candidate = Path(summary_path).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate

    if not candidate.is_file():
        # Try resolving relative to configured reports root when available.
        reports_root = os.getenv("REPORTS_ROOT")
        if reports_root:
            alt_candidate = Path(reports_root).expanduser() / summary_path
            if alt_candidate.is_file():
                candidate = alt_candidate

    if not candidate.is_file():
        raise CodegenError(f"Summary file '{summary_path}' was not found")

    try:
        with candidate.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive guard
        raise CodegenError(f"Summary file '{candidate}' is not valid JSON: {exc}") from exc


def _select_summary_task(
    payload: Dict[str, Any],
    task_name: Optional[str],
    task_index: int,
) -> Dict[str, Any]:
    """Return the selected task entry from ``payload``."""

    tasks = payload.get("summary")
    if not isinstance(tasks, Iterable):
        raise CodegenError("Summary payload does not contain a 'summary' list")

    if task_name:
        for entry in tasks:
            if isinstance(entry, dict) and entry.get("name") == task_name:
                return entry
        raise CodegenError(
            f"Task named '{task_name}' could not be located inside the summary"
        )

    try:
        entry = list(tasks)[task_index]
    except IndexError as exc:
        raise CodegenError(
            f"Summary index {task_index} is out of range for the available tasks"
        ) from exc

    if not isinstance(entry, dict):
        raise CodegenError("Selected summary entry is not an object")
    return entry


def _build_messages(
    task_entry: Dict[str, Any],
    *,
    metadata: Dict[str, Any],
    function_name: str,
) -> list[dict[str, Any]]:
    """Create the chat completion messages for the codegen request."""

    task_json = json.dumps(task_entry, indent=2, ensure_ascii=False)
    metadata_json = json.dumps(metadata, indent=2, ensure_ascii=False)

    system_prompt = (
        "You are a senior QA automation engineer specialising in pytest and Appium. "
        "Given an exploratory automation run summary you must craft a deterministic, "
        "maintainable pytest module that reproduces the intended scenario for future "
        "regression coverage. You know how to translate structured step data into "
        "Appium interactions, add resilient waits, and codify assertions that capture "
        "the expected behaviour."
    )

    user_prompt = (
        "Produce Python source code for a pytest module that exercises the described "
        "scenario. Follow these guidelines:\n"
        "1. Output only valid Python code with no Markdown fences or commentary.\n"
        "2. Target the Appium Python client for iOS automation.\n"
        "3. Provide all necessary imports, including pytest, typing hints, "
        "AppiumBy, WebDriverWait, expected_conditions, and Optional.\n"
        "4. Create a pytest fixture named 'ios_driver' that builds an Appium "
        "driver using an Appium server URL sourced from the APPIUM_SERVER_URL "
        "environment variable (default to http://localhost:4723) and placeholder "
        "desired capabilities with TODO comments for values that must be customised.\n"
        "5. Implement helper functions as needed to keep the test readable, such as "
        "`tap` or `enter_text` using WebDriverWait for element lookup.\n"
        "6. Define a test function named '{function_name}' that invokes the fixture.\n"
        "7. Translate each step in the run summary into clear test logic with "
        "explanatory comments derived from the step explanations.\n"
        "8. Convert 'tap' actions into `.click()` calls, 'input' actions into "
        "`clear()` + `send_keys()`, and incorporate assertions for error or "
        "validation steps when applicable.\n"
        "9. Assert on the final expected outcome using the information from the "
        "summary (for example, verifying alert text).\n"
        "10. The resulting module must be immediately executable with pytest without "
        "manual editing beyond filling in TODO placeholders.\n\n"
        "Automation metadata:\n"
        f"{metadata_json}\n\n"
        "Scenario summary entry:\n"
        f"{task_json}"
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def generate_pytest_from_summary(
    summary: Dict[str, Any],
    *,
    task_name: Optional[str] = None,
    task_index: int = 0,
    model: Optional[str] = None,
    temperature: float = 0.0,
    max_output_tokens: Optional[int] = None,
) -> CodegenResult:
    """Generate pytest automation code from a run ``summary``."""

    task_entry = _select_summary_task(summary, task_name, task_index)

    function_name = f"test_{_slugify(task_entry.get('name', 'scenario'))}"
    metadata = {
        key: value
        for key, value in summary.items()
        if key not in {"summary", "summary_path"}
    }
    metadata["reports_path"] = task_entry.get("reports_path") or summary.get(
        "summary_path"
    )

    messages = _build_messages(task_entry, metadata=metadata, function_name=function_name)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise CodegenError("OPENAI_API_KEY environment variable is required for codegen")

    base_url = (
        os.getenv("OPENAI_CODEGEN_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or None
    )
    model_name = (
        model
        or os.getenv("OPENAI_CODEGEN_MODEL")
        or os.getenv("OPENAI_MODEL")
    )

    if not model_name:
        raise CodegenError("No OpenAI model configured for code generation")

    client_kwargs = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url

    logger.debug(
        "Requesting pytest code generation using model '%s' (task: %s)",
        model_name,
        task_entry.get("name"),
    )

    client = OpenAI(**client_kwargs)
    request_kwargs: Dict[str, Any] = {
        "model": model_name,
        "messages": messages,
        "temperature": temperature,
    }
    if max_output_tokens is not None:
        request_kwargs["max_tokens"] = max_output_tokens

    try:
        response = client.chat.completions.create(**request_kwargs)
    except Exception as exc:  # pragma: no cover - network failure
        raise CodegenError(f"Code generation failed: {exc}") from exc

    choice = response.choices[0]
    content = choice.message.content if choice.message else None
    if not content:
        raise CodegenError("Code generation response did not contain any content")

    code = _strip_code_fences(content)
    if not code:
        raise CodegenError("Generated code was empty after stripping code fences")

    return CodegenResult(
        code=code,
        model=response.model or model_name,
        task_name=task_entry.get("name"),
        function_name=function_name,
    )


async def async_generate_pytest_from_path(
    summary_path: str,
    *,
    task_name: Optional[str] = None,
    task_index: int = 0,
    model: Optional[str] = None,
    temperature: float = 0.0,
    max_output_tokens: Optional[int] = None,
) -> CodegenResult:
    """Asynchronously load a summary from ``summary_path`` and generate pytest code."""

    def _load_and_generate() -> CodegenResult:
        payload = _load_summary_from_path(summary_path)
        return generate_pytest_from_summary(
            payload,
            task_name=task_name,
            task_index=task_index,
            model=model,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )

    return await asyncio.to_thread(_load_and_generate)
