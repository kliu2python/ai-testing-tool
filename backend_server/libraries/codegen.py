"""Utilities for generating test code from automation summaries."""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
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


_DEFAULT_CAPABILITIES: Dict[str, Dict[str, Any]] = {
    "android": {
        "platformName": "Android",
        "automationName": "uiautomator2",
        "deviceName": "google_api",
        "language": "en",
        "locale": "US",
        "appium:newCommandTimeout": 0,
        "appium:uiautomator2ServerLaunchTimeout": 0,
        "appium:noReset": True,
    },
    "ios": {
        "appium:xcodeSigningId": "App Development",
        "appium:automationName": "XCUITest",
        "platformName": "iOS",
        "appium:deviceName": "iPhone8-ios16",
        "appium:udid": "f67d7ce40691d9ab546d7362a4cc7a6182870de2",
        "appium:bundleId": "FortiToken-Mobile",
        "appium:wdaLocalPort": "8101",
    },
}


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


def _is_ios_input_step(step: Any) -> bool:
    """Return ``True`` when ``step`` represents an iOS text input action."""

    if not isinstance(step, dict):
        return False

    action = str(step.get("action", "")).strip().lower()
    if action != "input":
        return False

    platform = str(step.get("platform", "")).strip().lower()
    if platform and "ios" not in platform:
        return False

    return True


def _has_keyboard_confirmation(steps: list[Any], start_index: int) -> bool:
    """Return ``True`` if steps after ``start_index`` already tap the Done key."""

    confirmation_terms = {"done", "return", "go", "enter", "submit"}

    for candidate in steps[start_index + 1 :]:
        if not isinstance(candidate, dict):
            continue

        action = str(candidate.get("action", "")).strip().lower()
        if action == "wait":
            # Skip passive waits while searching for the next meaningful action.
            continue

        selector = str(candidate.get("selector", "")).strip().lower()
        label = str(candidate.get("label", "")).strip().lower()
        operation = str(candidate.get("operation", "")).strip().lower()
        explanation = str(candidate.get("explanation", "")).strip().lower()

        if action in {"tap", "click"}:
            if selector in confirmation_terms or label in confirmation_terms:
                return True
            if operation in confirmation_terms:
                return True
            if "keyboard" in explanation and any(
                term in explanation for term in confirmation_terms
            ):
                return True

        # Once a non-wait action is seen we stop searching further ahead.
        return False

    return False


def _build_synthetic_done_step(step: dict[str, Any]) -> dict[str, Any]:
    """Create a synthetic tap action that dismisses the iOS keyboard."""

    follow_up: dict[str, Any] = {
        "action": "tap",
        "operation": "enter",
        "strategy": "accessibility_id",
        "selector": "Done",
        "explanation": (
            "Tap the keyboard's Done button to confirm the text entry and dismiss the "
            "iOS keyboard when the original run omitted the action."
        ),
        "result": "success",
    }

    for key in ("target", "platform"):
        if key in step:
            follow_up[key] = step[key]

    if "platform" not in follow_up:
        follow_up["platform"] = "ios"

    return follow_up


def _ensure_keyboard_follow_ups(task_entry: Dict[str, Any]) -> Dict[str, Any]:
    """Inject synthetic keyboard confirmation steps for iOS text entry actions."""

    steps = task_entry.get("steps")
    if not isinstance(steps, list):
        return task_entry

    augmented_steps: list[Any] = []
    added_follow_up = False

    for index, step in enumerate(steps):
        augmented_steps.append(step)

        if not _is_ios_input_step(step):
            continue

        if _has_keyboard_confirmation(steps, index):
            continue

        augmented_steps.append(_build_synthetic_done_step(step))
        added_follow_up = True

    if added_follow_up:
        task_entry = dict(task_entry)
        task_entry["steps"] = augmented_steps

    return task_entry


def _safe_trimmed_str(value: Any) -> Optional[str]:
    """Return ``value`` stripped when it is a non-empty string."""

    if isinstance(value, str):
        trimmed = value.strip()
        if trimmed:
            return trimmed
    return None


def _load_run_request_payload(run_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """Fetch the stored run request payload for ``run_id`` when available."""

    if not run_id:
        return None

    try:
        from backend_server import task_store  # lazy import to avoid circular deps
    except Exception:  # pragma: no cover - import guard
        return None

    try:
        conn = task_store._connect()
    except Exception:  # pragma: no cover - database unavailable
        logger.debug("Failed to open task store connection", exc_info=True)
        return None

    try:
        task_store.ensure_task_tables(conn)
        cursor = conn.execute(
            "SELECT request_json FROM task_runs WHERE id = ?",
            (run_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        raw_value = row["request_json"] if isinstance(row, sqlite3.Row) else row[0]
        if not raw_value:
            return None
        return json.loads(raw_value)
    except Exception:  # pragma: no cover - defensive guard
        logger.debug("Failed to load request payload for run %s", run_id, exc_info=True)
        return None
    finally:
        conn.close()


def _collect_targets_from_payload(payload: Any) -> list[Dict[str, Any]]:
    """Return a list of target configuration dictionaries."""

    if not isinstance(payload, dict):
        return []

    targets = payload.get("targets")
    if not isinstance(targets, Iterable):
        return []

    result: list[Dict[str, Any]] = []
    for item in targets:
        if isinstance(item, dict):
            result.append(dict(item))
    return result


def _collect_step_context(task_entry: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """Return the first target alias and platform seen within the task steps."""

    target_alias: Optional[str] = None
    platform: Optional[str] = None
    steps = task_entry.get("steps")
    if isinstance(steps, Iterable):
        for step in steps:
            if not isinstance(step, dict):
                continue
            if target_alias is None:
                alias = _safe_trimmed_str(
                    step.get("target")
                    or step.get("device")
                    or step.get("session")
                )
                if alias:
                    target_alias = alias
            if platform is None:
                platform_hint = _safe_trimmed_str(
                    step.get("platform")
                    or step.get("platformName")
                    or step.get("platform_name")
                )
                if platform_hint:
                    platform = platform_hint.lower()
            if target_alias and platform:
                break
    return target_alias, platform


def _extract_driver_context(
    summary_payload: Any,
    metadata: Dict[str, Any],
    task_entry: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Derive driver configuration details for ``task_entry``."""

    run_request = metadata.get("run_request")
    if not isinstance(run_request, dict):
        run_request = _load_run_request_payload(task_entry.get("task_id"))
        if run_request:
            metadata["run_request"] = run_request

    targets: list[Dict[str, Any]] = []
    for source in (metadata, run_request, summary_payload):
        targets.extend(_collect_targets_from_payload(source))

    selected_alias, platform = _collect_step_context(task_entry)

    selected_target: Optional[Dict[str, Any]] = None
    if targets:
        lookup = {
            _safe_trimmed_str(
                item.get("name")
                or item.get("alias")
                or item.get("id")
            ).lower(): item
            for item in targets
            if _safe_trimmed_str(
                item.get("name")
                or item.get("alias")
                or item.get("id")
            )
        }
        if selected_alias and selected_alias.lower() in lookup:
            selected_target = dict(lookup[selected_alias.lower()])
        else:
            default_target = next(
                (
                    dict(item)
                    for item in targets
                    if isinstance(item, dict) and item.get("default")
                ),
                None,
            )
            selected_target = default_target or dict(targets[0])

    if platform is None:
        platform_source = (
            selected_target.get("platform")
            if isinstance(selected_target, dict)
            else None
        ) or metadata.get("platform")
        if not platform_source and isinstance(run_request, dict):
            platform_source = run_request.get("platform")
        platform_candidate = _safe_trimmed_str(platform_source)
        platform = platform_candidate.lower() if platform_candidate else None

    server_url: Optional[str] = None
    server_source = None
    if isinstance(selected_target, dict):
        server_candidate = _safe_trimmed_str(selected_target.get("server"))
        if server_candidate:
            server_url = server_candidate
            server_source = "target"

    if server_url is None and isinstance(run_request, dict):
        server_candidate = _safe_trimmed_str(run_request.get("server"))
        if server_candidate:
            server_url = server_candidate
            server_source = "request"

    if server_url is None:
        server_candidate = _safe_trimmed_str(metadata.get("server"))
        if server_candidate:
            server_url = server_candidate
            server_source = "metadata"

    capabilities: Optional[Dict[str, Any]] = None
    if isinstance(selected_target, dict):
        for key in ("capabilities", "desired_capabilities", "options"):
            value = selected_target.get(key)
            if isinstance(value, dict):
                capabilities = dict(value)
                break

    if capabilities is None and isinstance(run_request, dict):
        for key in ("capabilities", "desired_capabilities"):
            value = run_request.get(key)
            if isinstance(value, dict):
                capabilities = dict(value)
                break

    if capabilities is None and platform in _DEFAULT_CAPABILITIES:
        capabilities = copy.deepcopy(_DEFAULT_CAPABILITIES[platform])

    if not any((server_url, platform, capabilities, selected_alias)):
        return None

    context: Dict[str, Any] = {}
    if selected_alias:
        context["target_alias"] = selected_alias
    if platform:
        context["platform"] = platform
    if server_url:
        context["server_url"] = server_url
    if server_source:
        context["server_source"] = server_source
    if capabilities:
        context["capabilities"] = capabilities

    return context or None


def _suggest_fixture_name(driver_context: Optional[Dict[str, Any]]) -> str:
    """Return a descriptive fixture name based on ``driver_context``."""

    platform = (driver_context or {}).get("platform")
    if platform == "android":
        return "android_driver"
    if platform == "web":
        return "web_driver"
    return "ios_driver"


def _driver_instruction(
    driver_context: Optional[Dict[str, Any]],
    fixture_name: str,
) -> str:
    """Return instruction text for configuring the driver fixture."""

    snippet_instruction = (
        "   - Initialise the driver using this exact sequence, updating only the "
        "capabilities when necessary:\n"
        "options = XCUITestOptions()\n"
        "options.load_capabilities(caps)\n"
        "driver = webdriver.Remote(\"http://10.160.24.110:8080/wd/hub\", options=options)\n"
        "yield driver\n"
        "driver.quit()\n"
    )

    if not driver_context:
        return (
            f"4. Create a pytest fixture named '{fixture_name}' that builds an Appium "
            "driver using an Appium server URL sourced from the APPIUM_SERVER_URL "
            "environment variable (default to http://localhost:4723) and placeholder "
            "desired capabilities with TODO comments for values that must be customised.\n"
            f"{snippet_instruction}"
        )

    server_url = driver_context.get("server_url") or "http://localhost:4723"
    platform = driver_context.get("platform")
    alias = driver_context.get("target_alias")
    capabilities = driver_context.get("capabilities")

    details: list[str] = []
    details.append(
        f"4. Create a pytest fixture named '{fixture_name}' that builds an Appium driver "
        f"using the recorded server '{server_url}'."
    )
    if platform:
        details.append(f"   - Platform: {platform}")
    if alias:
        details.append(f"   - Target alias used during the run: {alias}")
    if capabilities:
        capabilities_json = json.dumps(capabilities, indent=2, ensure_ascii=False)
        details.append("   - Desired capabilities (use exactly as captured):")
        details.append(capabilities_json)
    else:
        details.append(
            "   - Provide concrete desired capabilities appropriate for this platform."
        )
    details.append(snippet_instruction.rstrip("\n"))
    return "\n".join(details) + "\n"


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
            data = json.load(handle)
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive guard
        raise CodegenError(f"Summary file '{candidate}' is not valid JSON: {exc}") from exc

    payload: Dict[str, Any]
    if isinstance(data, dict):
        payload = dict(data)
    else:
        payload = {"summary": data}

    payload.setdefault("summary_path", str(candidate))
    return payload


def _select_summary_task(
    payload: Any,
    task_name: Optional[str],
    task_index: int,
) -> Dict[str, Any]:
    """Return the selected task entry from ``payload``."""

    if isinstance(payload, dict):
        tasks = payload.get("summary")
    elif isinstance(payload, Iterable):
        tasks = payload
    else:  # pragma: no cover - defensive guard
        raise CodegenError("Summary payload is neither an object nor a list")

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
    fixture_name: str,
) -> list[dict[str, Any]]:
    """Create the chat completion messages for the codegen request."""

    task_json = json.dumps(task_entry, indent=2, ensure_ascii=False)
    metadata_json = json.dumps(metadata, indent=2, ensure_ascii=False)
    driver_instruction = _driver_instruction(
        metadata.get("driver_context"), fixture_name
    )

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
        "AppiumBy, WebDriverWait, expected_conditions, Optional, webdriver, and "
        "XCUITestOptions.\n"
        f"{driver_instruction}"
        "5. Implement helper functions as needed to keep the test readable, such as "
        "`tap` or `enter_text` using WebDriverWait for element lookup.\n"
        f"6. Define a test function named '{function_name}' that invokes the "
        f"'{fixture_name}' fixture.\n"
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
    summary: Any,
    *,
    task_name: Optional[str] = None,
    task_index: int = 0,
    model: Optional[str] = None,
    temperature: float = 0.0,
    max_output_tokens: Optional[int] = None,
) -> CodegenResult:
    """Generate pytest automation code from a run ``summary``."""

    if isinstance(summary, list):
        summary_payload: Dict[str, Any] = {"summary": summary}
    elif isinstance(summary, dict):
        summary_payload = summary
    else:
        raise CodegenError("Summary data must be an object or list of tasks")

    task_entry = copy.deepcopy(
        _select_summary_task(summary_payload, task_name, task_index)
    )
    task_entry = _ensure_keyboard_follow_ups(task_entry)

    function_name = f"test_{_slugify(task_entry.get('name', 'scenario'))}"
    metadata = (
        {
            key: value
            for key, value in summary_payload.items()
            if key not in {"summary", "summary_path"}
        }
        if isinstance(summary_payload, dict)
        else {}
    )
    metadata["reports_path"] = task_entry.get("reports_path") or (
        summary_payload.get("summary_path") if isinstance(summary_payload, dict) else None
    )

    driver_context = _extract_driver_context(summary_payload, metadata, task_entry)
    if driver_context:
        metadata["driver_context"] = driver_context

    fixture_name = _suggest_fixture_name(driver_context)
    messages = _build_messages(
        task_entry,
        metadata=metadata,
        function_name=function_name,
        fixture_name=fixture_name,
    )

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
