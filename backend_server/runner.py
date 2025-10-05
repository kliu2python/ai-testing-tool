from __future__ import annotations

import argparse
import asyncio
import base64
import datetime
import json
import logging
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
from time import sleep
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse, urlunparse

from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.options.ios import XCUITestOptions
from appium.webdriver.client_config import AppiumClientConfig
from appium.webdriver.common.appiumby import AppiumBy
from html.parser import HTMLParser
from openai import OpenAI
from selenium import webdriver as selenium_webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    WebDriverException,
    NoSuchWindowException
)
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.options import Options as ChromeOptions
from PIL import Image, ImageDraw, ImageFont
import xml.etree.ElementTree as ET
import yaml
from dotenv import load_dotenv

from backend_server.libraries.taas.dhub import Dhub
from backend_server.logging_config import configure_logging

load_dotenv()

configure_logging()
logger = logging.getLogger(__name__)


@dataclass
class RunResult:
    """Container for aggregated run results."""

    summary: List[Dict[str, Any]]
    summary_path: str


@dataclass
class TargetContext:
    """Runtime metadata for an automation target/driver."""

    name: str
    platform: str
    server: str
    driver: Any
    page_source: Optional[str] = None
    screenshot: Optional[str] = None
    screen_description: Optional[str] = None
    keepalive_thread: Optional[threading.Thread] = None


_EXECUTOR: Optional[ThreadPoolExecutor] = None
_EXECUTOR_LOCK = threading.Lock()


def _get_executor() -> ThreadPoolExecutor:
    """Return a lazily initialised thread pool for background runs."""

    global _EXECUTOR
    with _EXECUTOR_LOCK:
        if _EXECUTOR is None:
            max_workers = int(os.getenv("RUNNER_MAX_WORKERS", "4"))
            _EXECUTOR = ThreadPoolExecutor(max_workers=max_workers)
    return _EXECUTOR


# -----------------------------
# File & image helpers
# -----------------------------
def read_file_content(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            content = file.read()
        return content
    except FileNotFoundError:
        logger.error("The file '%s' does not exist.", file_path)
    except IOError:
        logger.error("Unable to read the file '%s'.", file_path)


def create_folder(folder_path):
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
    return folder_path


def _normalise_target_name(name: str) -> str:
    """Return a filesystem-friendly representation of ``name``."""

    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", (name or "").strip())
    cleaned = cleaned.strip("_")
    return cleaned or "target"


def _choose_target_alias(
    targets: Dict[str, TargetContext],
    desired_alias: Optional[str],
    platform_hint: Optional[str],
    default_alias: str,
) -> Tuple[str, Optional[str]]:
    """Resolve which target alias should be used for an action.

    Returns the selected alias and an optional error message when the requested
    alias/platform could not be matched.
    """

    if desired_alias:
        alias = str(desired_alias)
        if alias in targets:
            return alias, None
        return default_alias, f"unknown target '{alias}'"

    if platform_hint:
        platform = str(platform_hint).lower()
        for alias, ctx in targets.items():
            if (ctx.platform or "").lower() == platform:
                return alias, None
        return default_alias, f"no target configured for platform '{platform_hint}'"

    return default_alias, None


def _step_page_name(step_index: int, target_alias: str, multi_target: bool) -> str:
    base = f"step{step_index}"
    if multi_target:
        base = f"{base}_{_normalise_target_name(target_alias)}"
    return base


def _step_screenshot_name(step_index: int, target_alias: str, multi_target: bool) -> str:
    base = f"step_{step_index}"
    if multi_target:
        base = f"{base}_{_normalise_target_name(target_alias)}"
    return base


def image_to_base64(image_path: str) -> Optional[str]:
    try:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")
    except FileNotFoundError:
        logger.warning("Screenshot '%s' is not available for encoding", image_path)
    except IOError as exc:
        logger.warning("Unable to read screenshot '%s': %s", image_path, exc)
    return None


# -----------------------------
# LLM: next action generation
# -----------------------------
_LLM_MODES = {"auto", "text", "vision"}
_VISION_KEYWORDS = {
    "image",
    "visual",
    "screenshot",
    "picture",
    "photo",
    "icon",
    "diagram",
    "graph",
    "chart",
    "camera",
    "ocr",
    "scan",
}


def _normalise_llm_mode(mode: Optional[str]) -> str:
    if not mode:
        return "auto"
    mode_lower = mode.lower()
    if mode_lower not in _LLM_MODES:
        logger.debug("Unknown LLM mode '%s', defaulting to 'auto'", mode)
        return "auto"
    return mode_lower


def _task_needs_vision(task: Dict[str, Any]) -> bool:
    text_fragments: List[str] = []
    for key in ("details", "name"):
        value = task.get(key)
        if isinstance(value, str):
            text_fragments.append(value)

    steps = task.get("steps")
    if isinstance(steps, list):
        for step in steps:
            if isinstance(step, dict):
                for value in step.values():
                    if isinstance(value, str):
                        text_fragments.append(value)

    combined = " ".join(text_fragments).lower()
    return any(keyword in combined for keyword in _VISION_KEYWORDS)


def _resolve_task_llm_mode(preference: Optional[str], task: Dict[str, Any]) -> str:
    normalised = _normalise_llm_mode(preference)
    if normalised == "auto":
        selected = "vision" if _task_needs_vision(task) else "text"
        logger.debug(
            "Auto-select LLM mode '%s' for task '%s'", selected, task.get("name")
        )
        return selected
    return normalised


def _describe_screenshot_with_vision_model(screenshot_path: str) -> Optional[str]:
    """Return a textual description of ``screenshot_path`` using the vision model."""

    screenshot_base64 = image_to_base64(screenshot_path)
    if not screenshot_base64:
        return None

    api_key = os.getenv("OPENAI_VISION_API_KEY")
    model = os.getenv("OPENAI_VISION_MODEL")
    if not api_key or not model:
        logger.warning(
            "Vision mode requested but OPENAI_VISION_API_KEY or OPENAI_VISION_MODEL is not set; "
            "skipping screenshot description",
        )
        return None

    base_url = os.getenv("OPENAI_VISION_BASE_URL") or os.getenv("OPENAI_BASE_URL")

    client_kwargs = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url

    system_prompt = (
        "You are an assistant that describes application screenshots for automated testing. "
        "Identify interactive controls, text labels, alerts, and any relevant UI layout details."
    )
    user_message = [
        {
            "type": "text",
            "text": (
                "Provide a concise yet thorough description of the visible screen. "
                "Highlight key UI elements, their labels, and any state that might influence the next action."
            ),
        },
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{screenshot_base64}"},
        },
    ]

    try:
        client = OpenAI(**client_kwargs)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )
    except Exception as exc:
        logger.warning("Vision model failed to describe screenshot '%s': %s", screenshot_path, exc)
        return None

    description = response.choices[0].message.content or ""
    return description.strip() or None


def generate_next_action(
    _prompt: str,
    _task: str,
    _history_actions: List[str],
    page_source_file: str,
    screenshot_path: Optional[str],
    llm_mode: str,
    screen_description: Optional[str] = None,
    available_targets: Optional[Dict[str, Dict[str, str]]] = None,
    active_target: Optional[str] = None,
) -> str:
    resolved_mode = _normalise_llm_mode(llm_mode)
    _page_src = read_file_content(page_source_file) or ""
    _history_actions_str = "\n".join(_history_actions)

    if not screen_description and screenshot_path:
        screen_description = _describe_screenshot_with_vision_model(screenshot_path)
        logger.info(f"The screen description is {screen_description}")

    user_content: List[Dict[str, Any]] = [
        {"type": "text", "text": f"# Task \n {_task}"},
        {"type": "text", "text": f"# History of Actions \n {_history_actions_str}"},
        {"type": "text", "text": f"# Source of Page \n ```yaml\n {_page_src} \n```"},
    ]

    if screen_description:
        user_content.append(
            {"type": "text", "text": f"# Screen Description \n {screen_description}"}
        )
    if available_targets:
        target_lines = ["# Available Targets"]
        for alias, meta in available_targets.items():
            platform = meta.get("platform") if meta else None
            server = meta.get("server") if meta else None
            details = [f"platform={platform}" if platform else None]
            if server:
                details.append(f"server={server}")
            details = ", ".join(filter(None, details))
            if details:
                target_lines.append(f"- {alias}: {details}")
            else:
                target_lines.append(f"- {alias}")
        target_lines.append(
            "When proposing an action JSON include a 'target' field to choose "
            "which device/session should execute it."
        )
        target_lines.append(
            "Omit the 'target' field to keep using the active context."
        )
        user_content.append({"type": "text", "text": "\n".join(target_lines)})

    if active_target:
        user_content.append(
            {"type": "text", "text": f"# Active Target \n {active_target}"}
        )
    elif resolved_mode == "vision":
        logger.debug(
            "Vision mode requested but no screenshot description was generated for '%s'",
            screenshot_path,
        )

    system_prompt = _prompt
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable is required")

    base_url = os.getenv("OPENAI_BASE_URL")
    model = os.getenv("OPENAI_MODEL")

    if not model:
        raise RuntimeError("No OpenAI model configured for next action generation")

    client_kwargs = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url

    open_ai = OpenAI(**client_kwargs)
    chat_response = open_ai.chat.completions.create(model=model, messages=messages)
    content = chat_response.choices[0].message.content
    return content


# -------------------------------------------------------
# Drivers (multi-app friendly)
# -------------------------------------------------------
def _truthy(value: Optional[str]) -> bool:
    """Return ``True`` when ``value`` represents a truthy string."""

    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _normalise_appium_server(server: str) -> str:
    """Normalise the supplied Appium server URL.

    * Adds a default scheme (``APPIUM_DEFAULT_SCHEME`` or ``http``) when one is
      omitted.
    * Upgrades ``http`` URLs to ``https`` when ``APPIUM_FORCE_TLS`` is truthy.
    """

    server = server.strip()
    if not server:
        raise ValueError("Appium server URL must not be empty")

    default_scheme = os.getenv("APPIUM_DEFAULT_SCHEME", "http")
    force_tls = _truthy(os.getenv("APPIUM_FORCE_TLS"))

    if "://" not in server:
        server = f"{default_scheme}://{server}"

    parsed = urlparse(server)
    if force_tls and parsed.scheme.lower() == "http":
        parsed = parsed._replace(scheme="https")
        server = urlunparse(parsed)

    return server


def _appium_client_config(server: str) -> Optional[AppiumClientConfig]:
    """Build a TLS aware ``AppiumClientConfig`` when needed."""

    ignore_certs = _truthy(os.getenv("APPIUM_IGNORE_CERTIFICATES"))
    ca_certs = os.getenv("APPIUM_CA_CERTS") or None
    timeout_env = os.getenv("APPIUM_CLIENT_TIMEOUT")
    timeout = None
    if timeout_env:
        try:
            timeout = int(timeout_env)
        except ValueError as exc:
            raise ValueError("APPIUM_CLIENT_TIMEOUT must be an integer") from exc

    if not any([ignore_certs, ca_certs, timeout]) and not server.lower().startswith("https://"):
        return None

    return AppiumClientConfig(
        server,
        ignore_certificates=ignore_certs,
        ca_certs=ca_certs,
        timeout=timeout,
    )


def _needs_wd_hub_retry(error: Exception) -> bool:
    """Return ``True`` when ``error`` indicates an Appium base-path issue."""

    message = getattr(error, "msg", None) or str(error)
    if not message:
        return False
    lowered = message.lower()
    if "requested resource could not be found" in lowered:
        return True
    if "404" in lowered and "wd/hub" in lowered:
        return True
    return False


def _append_wd_hub(server: str) -> str:
    """Append ``/wd/hub`` to ``server`` when it is missing."""

    parsed = urlparse(server)
    path = parsed.path or ""
    trimmed = path.rstrip("/")
    if trimmed.endswith("wd/hub"):
        return server
    if trimmed:
        new_path = f"{trimmed}/wd/hub"
    else:
        new_path = "/wd/hub"
    return urlunparse(parsed._replace(path=new_path))


def reopen_app(_driver, app_name: str = "com.fortinet.android.ftm"):
    _driver.terminate_app(app_name, timeout=3000)
    _driver.activate_app(app_name)


def create_driver(_server, _platform="android",
                  extra_caps: Optional[Dict[str, Any]] = None):
    extra_caps = extra_caps or {}
    platform = _platform.lower()

    server: Optional[str] = None
    client_config: Optional[AppiumClientConfig] = None
    if platform in {"android", "ios"}:
        server = _normalise_appium_server(_server)
        client_config = _appium_client_config(server)

    if platform == "android":
        capabilities = {
            "platformName": "Android",
            "automationName": "uiautomator2",
            "deviceName": "google_api",
            "language": "en",
            "locale": "US",
            "appium:newCommandTimeout": 0,
            "appium:uiautomator2ServerLaunchTimeout": 0,
            "appium:noReset": True,
            }
        capabilities.update(extra_caps)
        assert server is not None
        options = UiAutomator2Options().load_capabilities(capabilities)

        def _connect(target: str):
            return webdriver.Remote(
                target,
                options=options,
                client_config=client_config,
            )

        try:
            _driver = _connect(server)
            reopen_app(_driver)
            return _driver
        except WebDriverException as exc:
            if _needs_wd_hub_retry(exc):
                fallback = _append_wd_hub(server)
                if fallback != server:
                    logger.info("Retrying Appium connection with '/wd/hub' base path")
                    return _connect(fallback)
            raise

    if platform == "ios":
        capabilities = {
            "appium:xcodeSigningId": "App Development",
            "appium:automationName": "XCUITest",
            "platformName": "iOS",
            "appium:deviceName": "iPhone8-ios16",
            "appium:udid": "f67d7ce40691d9ab546d7362a4cc7a6182870de2",
            "appium:autoLaunch": False,
            "appium:noReset": True,
            "appium:wdaLocalPort": "8101",
            }
        capabilities.update(extra_caps)
        assert server is not None
        options = XCUITestOptions().load_capabilities(capabilities)

        def _connect(target: str):
            return webdriver.Remote(
                target,
                options=options,
                client_config=client_config,
            )

        try:
            return _connect(server)
        except WebDriverException as exc:
            if _needs_wd_hub_retry(exc):
                fallback = _append_wd_hub(server)
                if fallback != server:
                    logger.info("Retrying Appium connection with '/wd/hub' base path")
                    return _connect(fallback)
            raise

    if platform == "web":
        dhub_obj = Dhub(
            browser="chrome",
            version="125.0",
            resolutions='1920x1080',
            ram='6Gi'
            )
        dhub_obj.create_selenium_pod()
        count = 20
        node_ready = False
        while count > 0:
            status = dhub_obj.check_selenium_node()
            logger.debug("Selenium node readiness status: %s", status)
            if status:
                node_ready = True
                break
            sleep(3)
            count -= 1
        if not node_ready:
            raise WebDriverException('WebDriver is not ready')
        chrome_options = ChromeOptions()
        chrome_options.platform_name = "linux"
        chrome_options.browser_version = '125.0'
        chrome_options.set_capability('nodename:applicationName',
                                      dhub_obj.node_name)
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--ignore-certificate-errors")
        chrome_options.add_argument("--remote-debugging-pipe")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.set_capability("acceptInsecureCerts", True)
        return selenium_webdriver.Remote(
            command_executor="http://10.160.24.17:31590",
            options=chrome_options
            )

    raise ValueError(f"Unsupported platform: {_platform}")


def _prepare_target_contexts(
    server: Optional[str],
    platform: Optional[str],
    targets: Optional[List[Dict[str, Any]]],
) -> Tuple[Dict[str, TargetContext], str]:
    """Create drivers for all requested targets and return them."""

    configs: List[Tuple[str, str, str, bool]] = []
    base_server = (server or "").strip()

    if targets:
        for index, raw_cfg in enumerate(targets):
            cfg = dict(raw_cfg or {})
            alias = str(
                cfg.get("name")
                or cfg.get("alias")
                or cfg.get("id")
                or f"target{index + 1}"
            )
            target_platform = cfg.get("platform") or platform
            raw_target_server = cfg.get("server")
            target_server = (raw_target_server or base_server or "").strip()
            if not target_platform:
                raise ValueError(
                    f"Target '{alias}' is missing a platform configuration"
                )
            if not target_server:
                raise ValueError(
                    f"Target '{alias}' is missing an automation server"
                )
            is_default = bool(cfg.get("default") or cfg.get("is_default"))
            configs.append((alias, str(target_server), str(target_platform), is_default))
    else:
        if not platform:
            raise ValueError(
                "A platform must be provided when no targets are configured"
            )
        if not base_server:
            raise ValueError(
                "An automation server must be provided when no targets are configured"
            )
        alias = platform or "default"
        configs.append((alias, base_server, platform, True))

    contexts: Dict[str, TargetContext] = {}
    default_alias: Optional[str] = None
    created: List[TargetContext] = []

    try:
        for alias, target_server, target_platform, is_default in configs:
            if alias in contexts:
                raise ValueError(f"Duplicate target alias '{alias}'")

            driver = create_driver(target_server, target_platform)
            driver.implicitly_wait(0.2)
            keepalive_thread = threading.Thread(
                target=lambda d=driver: keep_driver_live(d), daemon=True
            )
            keepalive_thread.start()

            ctx = TargetContext(
                name=alias,
                platform=str(target_platform).lower(),
                server=target_server,
                driver=driver,
                keepalive_thread=keepalive_thread,
            )
            contexts[alias] = ctx
            created.append(ctx)
            if is_default or default_alias is None:
                default_alias = alias
    except Exception:
        for ctx in created:
            try:
                ctx.driver.quit()
            except Exception:
                pass
        raise

    if not contexts:
        raise ValueError("At least one automation target is required")

    default_alias = default_alias or next(iter(contexts))

    return contexts, default_alias


# Helpers for app switching
def activate(driver, bundle_id_or_package: str, wait: float = 0.6):
    driver.activate_app(bundle_id_or_package)
    sleep(wait)


def terminate_if_running(driver, bundle_id_or_package: str):
    try:
        driver.terminate_app(bundle_id_or_package)
    except Exception:
        pass


# -----------------------------
# Image helpers (optional grid overlay)
# -----------------------------
def resize_image(img, max_long=2048, max_short=768):
    """Resize the image maintaining aspect ratio"""
    original_width, original_height = img.size
    aspect_ratio = original_width / original_height

    if aspect_ratio > 1:
        new_width = min(original_width, max_long)
        new_height = int(new_width / aspect_ratio)
        new_height = min(new_height, max_short)
        new_width = int(new_height * aspect_ratio)
    else:
        new_height = min(original_height, max_long)
        new_width = int(new_height * aspect_ratio)
        new_width = min(new_width, max_short)
        new_height = int(new_width / aspect_ratio)

    return img.resize((new_width, new_height))


def draw_grid_with_labels(image_path, grid_size, output_path):
    with Image.open(image_path) as img:
        width, height = img.size
        label_space = 30
        new_width = width + label_space
        new_height = height + label_space
        new_img = Image.new("RGB", (new_width, new_height), "white")
        new_img.paste(img, (label_space, label_space))
        draw = ImageDraw.Draw(new_img)

        try:
            font = ImageFont.truetype("arial.ttf", 14)
        except IOError:
            font = ImageFont.load_default()

        for x in range(label_space, new_width, grid_size):
            line = ((x, label_space), (x, new_height))
            draw.line(line, fill=128)
            draw.text((x - 5, 5),
                      str((x - label_space) // grid_size),
                      fill="black", font=font)

        for y in range(label_space, new_height, grid_size):
            line = ((label_space, y), (new_width, y))
            draw.line(line, fill=128)
            draw.text((5, y - 10),
                      str((y - label_space) // grid_size),
                      fill="black", font=font)

        resize_image(new_img).save(output_path)


def format_image(image_path, output_path):
    with Image.open(image_path) as img:
        width, height = img.size
        new_img = Image.new("RGB", (width, height), "white")
        new_img.paste(img)
        resize_image(new_img).save(output_path)


def write_to_file(file_path, string_to_write):
    with open(file_path, "w", encoding="utf-8") as file:
        file.write(string_to_write)
    return file_path


def write_to_file_with_line_filter(file_path, string_to_write, _filter):
    filtered_lines = [
        line.strip() for line in string_to_write.split("\\n") if _filter in line
        ]
    with open(file_path, "w", encoding="utf-8") as file:
        file.write("\\n".join(filtered_lines))
    return file_path


# -----------------------------
# Platform-aware attribute keepers for XML → YAML
# -----------------------------
ANDROID_ATTRS = {
    "index", "package", "class", "text", "resource-id", "content-desc",
    "clickable", "scrollable", "bounds", "enabled", "displayed",
    "checked", "selected", "password", "long-clickable", "focusable", "focused"
    }

IOS_ATTRS = {
    "value", "label", "name", "x", "y", "enabled",
    "width", "height", "visible", "accessible", "type", "index"
    }

WEB_ATTRS = {
    "id", "name", "type", "value", "placeholder",
    "aria-label", "role", "href", "for", "title", "alt", "class"
    }

COMMON_ATTRS = {"index"}


class _DOMNode:
    __slots__ = ("tag", "attrs", "children", "text")

    def __init__(self, tag, attrs):
        self.tag = tag
        self.attrs = dict(attrs)
        self.children = []
        self.text = ""


class _MiniHTMLParser(HTMLParser):
    def __init__(self, keep_attrs: set):
        super().__init__(convert_charrefs=True)
        self.keep_attrs = keep_attrs
        self.stack = []
        self.root = _DOMNode("document", {})
        self.stack.append(self.root)

    def handle_starttag(self, tag, attrs):
        filt_attrs = {k: v for k, v in attrs if k in self.keep_attrs and v}
        node = _DOMNode(tag, filt_attrs)
        self.stack[-1].children.append(node)
        self.stack.append(node)

    def handle_endtag(self, tag):
        if len(self.stack) > 1:
            self.stack.pop()

    def handle_data(self, data):
        s = data.strip()
        if s:
            # keep short visible text only to avoid huge dumps
            if len(s) > 200:
                s = s[:200] + "…"
            self.stack[-1].text += ((" " if self.stack[-1].text else "") + s)


def _dom_to_dict(node: _DOMNode) -> dict:
    res = {}
    # attributes first (filtered)
    if node.attrs:
        res.update(node.attrs)
    # include short text for leaf-ish nodes
    if node.text and len(node.text) <= 200:
        res["text"] = node.text
    # group children by tag (like your XML shape)
    groups = {}
    for c in node.children:
        groups.setdefault(c.tag, []).append(_dom_to_dict(c))
    res.update(groups)
    return res


def html_to_dict(html_str: str) -> Dict[str, Any]:
    parser = _MiniHTMLParser(WEB_ATTRS)
    parser.feed(html_str)
    # collapse under top-level document
    return {"html": _dom_to_dict(parser.root)}


def _coerce_scalar(s: str) -> Any:
    if s is None:
        return None
    ls = s.strip().lower()
    if ls in ("true", "false"):
        return ls == "true"
    try:
        if "." in ls:
            return float(ls)
        return int(ls)
    except ValueError:
        return s


def _attrs_whitelist(platform: str) -> set:
    p = (platform or "").lower()
    if p == "android":
        return ANDROID_ATTRS
    if p == "ios":
        return IOS_ATTRS
    return COMMON_ATTRS


def _detect_platform_from_xml(xml_str: str) -> str:
    if "XCUIElementType" in xml_str or "<AppiumAUT" in xml_str:
        return "ios"
    if "resource-id=" in xml_str or "content-desc=" in xml_str:
        return "android"
    return "unknown"


def _detect_platform_from_driver(driver) -> Optional[str]:
    try:
        caps = getattr(driver, "capabilities", {}) or {}
        p = (caps.get("platformName") or caps.get("platform") or "").lower()
        browser = (caps.get("browserName") or caps.get("browser") or "").lower()
        if browser:  # selenium web sessions expose browserName
            return "web"
        if p in ("android", "ios"):
            return p
    except Exception:
        pass
    return None


def remove_unexpected_attr(node: ET.Element, platform: str = "android"):
    keep = _attrs_whitelist(platform)
    unexpected_keys = [k for k in list(node.attrib.keys()) if k not in keep]
    for k in unexpected_keys:
        del node.attrib[k]
    for child in node:
        remove_unexpected_attr(child, platform)


def refine_xml(xml_str: str, platform: Optional[str] = None) -> str:
    if platform is None or platform.lower() not in ("android", "ios"):
        platform = _detect_platform_from_xml(xml_str)
    root = ET.fromstring(xml_str)
    remove_unexpected_attr(root, platform=platform)
    return ET.tostring(root, encoding="unicode")


def xml_to_dict(xml_element: ET.Element, platform: str = "android") -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for child in xml_element:
        child_payload = xml_to_dict(child, platform=platform)
        tag = child.tag
        if tag in result:
            result[tag].append(child_payload)
        else:
            result[tag] = [child_payload]

    if xml_element.text and xml_element.text.strip():
        text = xml_element.text.strip()
        if "content" in result:
            result["content"].append(text)
        else:
            result["content"] = [text]

    keep = _attrs_whitelist(platform)
    attribs = {k: _coerce_scalar(v) for k, v in xml_element.attrib.items()
                if k in keep and v and v.strip()}
    if attribs:
        result.update(attribs)

    return result


def xml_to_yaml(xml_file: str, yaml_file: str, platform: Optional[str] = None):
    xml_str = read_file_content(xml_file)
    if platform is None or platform.lower() not in ("android", "ios"):
        platform = _detect_platform_from_xml(xml_str)
    root = ET.fromstring(xml_str)
    xml_dict = xml_to_dict(root, platform=platform)
    yaml_data = yaml.safe_dump(xml_dict, default_flow_style=False, sort_keys=False)
    return write_to_file(yaml_file, yaml_data)


def xml_str_to_yaml(yaml_file: str, xml_str: str, platform: Optional[str] = None):
    if platform is None or platform.lower() not in ("android", "ios"):
        platform = _detect_platform_from_xml(xml_str)
    root = ET.fromstring(xml_str)
    xml_dict = xml_to_dict(root, platform=platform)
    yaml_data = yaml.safe_dump(xml_dict, default_flow_style=False, sort_keys=False)
    return write_to_file(yaml_file, yaml_data)


def html_str_to_yaml(yaml_file: str, html_str: str):
    html_dict = html_to_dict(html_str)
    yaml_data = yaml.safe_dump(html_dict, default_flow_style=False, sort_keys=False)
    return write_to_file(yaml_file, yaml_data)


def _wait_for_ready(driver, timeout=10):
    if _get_platform(driver) != "web":
        return
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script("return (document.readyState === 'complete')")
        )
    except Exception:
        pass  # don’t fail the test flow just because readyState check flaked


def _maybe_switch_to_new_window(driver, settle_ms: int = 600):
    """If a new window/tab opened, switch to it."""
    try:
        before = set(driver.window_handles)
    except Exception:
        before = set()
    sleep(settle_ms / 1000.0)
    try:
        after = set(driver.window_handles)
    except Exception:
        return
    new = list(after - before)
    if new:
        try:
            driver.switch_to.window(new[-1])
        except Exception:
            pass


def _safe_page_source(driver, retries=3):
    for _ in range(retries):
        try:
            return driver.page_source
        except NoSuchWindowException:
            try:
                handles = driver.window_handles
                if handles:
                    driver.switch_to.window(handles[-1])
                    continue
            except Exception:
                pass
        except WebDriverException:
            sleep(0.3)  # page likely mid-navigation
    return ""  # last resort, don’t kill the loop


def _switch_if_new_window(driver, before_handles):
    try:
        after = driver.window_handles
        new = [h for h in after if h not in before_handles]
        if new:
            driver.switch_to.window(new[-1])
            return True
    except Exception:
        pass
    return False


def take_page_source(driver, folder: str, name: str):
    xml_or_html_path = f"{folder}/{name}.xml"  # will switch to .html for web
    yaml_path = f"{folder}/{name}.yaml"
    src = _safe_page_source(driver)

    platform = _detect_platform_from_driver(driver) or _detect_platform_from_xml(src)

    if platform == "web":
        # Save raw HTML and also provide a YAML DOM outline for the LLM
        _wait_for_ready(driver, timeout=6)
        _maybe_switch_to_new_window(driver)
        html_path = f"{folder}/{name}.html"
        write_to_file(html_path, src)
        return html_str_to_yaml(yaml_path, src)
    else:
        # Mobile (Android/iOS) – save XML and YAML as before
        write_to_file(xml_or_html_path, src)
        return xml_str_to_yaml(yaml_path, src, platform=platform)


def take_screenshot(driver: webdriver.Remote, folder, name):
    driver.save_screenshot(f"{folder}/{name}.png")
    format_image(f"{folder}/{name}.png", f"{folder}/{name}.jpg")
    return f"{folder}/{name}.jpg"


# -----------------------------
# Actions processing
# -----------------------------
def parse_bounds(bounds):
    left_top, right_bottom = bounds.split("][")
    left, top = map(int, left_top[1:].split(","))
    right, bottom = map(int, right_bottom[:-1].split(","))
    return (left, top, right, bottom)


def _get_platform(_driver) -> str:
    try:
        caps = getattr(_driver, "capabilities", {}) or {}
        browser = (caps.get("browserName") or caps.get("browser") or "").lower()
        if browser:
            return "web"
        p = (caps.get("platformName") or caps.get("platform") or "").lower()
        if p in ("android", "ios"):
            return p
    except Exception:
        pass
    try:
        if "XCUIElementType" in _driver.page_source:
            return "ios"
    except Exception:
        pass
    return "android"


def _find_focused_element(driver, platform: str):
    try:
        if platform == "android":
            return driver.find_element(AppiumBy.XPATH, "//*[@focused='true']")
        else:
            try:
                return driver.find_element(AppiumBy.IOS_PREDICATE, "hasKeyboardFocus == 1")
            except NoSuchElementException:
                try:
                    return driver.switch_to.active_element
                except Exception:
                    return None
    except NoSuchElementException:
        return None


def _send_keys_safely(el, value: str, platform: str):
    try:
        el.send_keys(value)
        return True
    except WebDriverException:
        pass
    if platform == "ios":
        try:
            el.set_value(value)
            return True
        except WebDriverException:
            pass
    return False


def _hide_keyboard_safely(driver, platform: str):
    try:
        driver.hide_keyboard()
    except Exception:
        pass


# ---- App aliasing & per-task activation ----
APP_ALIASES_IOS: Dict[str, str] = {
    "settings": "com.apple.Preferences",
    "preferences": "com.apple.Preferences",
    "testflight": "com.apple.TestFlight",
    "fortitoken": "FortiToken-Mobile",
    "fortitoken-mobile": "FortiToken-Mobile",
}
APP_ALIASES_ANDROID: Dict[str, str] = {
    "settings": "com.android.settings",
    "fortitoken": "com.fortinet.android.ftm",
    "fortitoken-mobile": "com.fortinet.android.ftm",
}


def resolve_app_id(raw: str, platform: str) -> str:
    key = (raw or "").strip()
    if platform == "ios":
        return APP_ALIASES_IOS.get(key.lower(), key)
    if platform == "android":
        return APP_ALIASES_ANDROID.get(key.lower(), key)
    return key


def activate_sequence_for_task(driver, platform: str, apps: Optional[List[str]]):
    if not apps:
        return
    for app in apps:
        bundle_or_pkg = resolve_app_id(app, platform)
        try:
            driver.activate_app(bundle_or_pkg)
            sleep(0.6)
        except Exception as e:
            logger.warning("Failed to activate %s: %s", bundle_or_pkg, e)


def process_next_action(action, driver: webdriver.Remote, folder, step_name):
    logger.info(f"!!Action is {action}")
    data = safe_json_loads(action)
    platform = _get_platform(driver)
    if data["action"] in ("error", "finish"):
        take_page_source(driver, folder, step_name)
        take_screenshot(driver, folder, step_name)
        data["result"] = "success"
        return (None, None, json.dumps(data))

    try:
        if data["action"] in ["tap", "click"] and "bounds" in data:
            bounds = data["bounds"]
            left, top, right, bottom = parse_bounds(bounds)
            tap_x = left + (right - left) / 2
            tap_y = top + (bottom - top) / 2
            if platform == "web":
                # Best-effort JS click at viewport coords
                try:
                    driver.execute_script(
                        """
                            const x = arguments[0], y = arguments[1];
                            const el = document.elementFromPoint(x, y);
                            if (el) el.click();
                        """, int(tap_x), int(tap_y)
                        )
                    _maybe_switch_to_new_window(driver)
                    data["result"] = "success"
                except Exception as e:
                    data["result"] = f"web coordinate click failed: {e}"
            else:
                driver.tap([(tap_x, tap_y)])
                data["result"] = "success"

        elif data["action"] in ["tap", "click"] and "xpath" in data:
            xpath = data["xpath"]
            elements = driver.find_elements(AppiumBy.XPATH, xpath)
            if not elements:
                data["result"] = f"can't find element {xpath}"
            else:
                before = []
                if platform == "web":
                    try:
                        before = driver.window_handles[
                                 :]  # snapshot window handles
                    except Exception:
                        before = []
                elements[0].click()
                if platform == "web":
                    # If a new tab opened, switch to it; otherwise wait for load
                    switched = _switch_if_new_window(driver, before)
                    if not switched:
                        _wait_for_ready(driver, timeout=8)
                data["result"] = "success"

        elif data["action"] == "swipe":
            driver.swipe(
                data["swipe_start_x"],
                data["swipe_start_y"],
                data["swipe_end_x"],
                data["swipe_end_y"],
                data["duration"],
            )
            sleep(data["duration"] / 1000)
            data["result"] = "success"

        elif data["action"] in ("activate", "activate_app"):
            bundle_id = data.get("bundleId") or data.get("package") or data.get("app")
            if not bundle_id:
                data["result"] = "missing bundleId/package/app for activate_app"
            else:
                bundle_id = resolve_app_id(bundle_id, platform)
                try:
                    driver.activate_app(bundle_id)
                    sleep(0.5)
                    data["result"] = "success"
                except Exception as e:
                    data["result"] = f"activate_app failed: {e}"

        elif data["action"] == "terminate_app":
            bundle_id = data.get("bundleId") or data.get("package") or data.get("app")
            if not bundle_id:
                data["result"] = "missing bundleId/package/app for terminate_app"
            else:
                bundle_id = resolve_app_id(bundle_id, platform)
                try:
                    driver.terminate_app(bundle_id)
                    data["result"] = "success"
                except Exception as e:
                    data["result"] = f"terminate_app failed: {e}"

        elif data["action"] == "input" and "bounds" in data:
            bounds = data["bounds"]
            value = data["value"]
            left, top, right, bottom = parse_bounds(bounds)
            tap_x = left + (right - left) / 2
            tap_y = top + (bottom - top) / 2
            driver.tap([(tap_x, tap_y)])
            target = _find_focused_element(driver, platform)
            if target and _send_keys_safely(target, value, platform):
                _hide_keyboard_safely(driver, platform)
                data["result"] = "success"
            else:
                if platform == "ios":
                    try:
                        driver.execute_script("mobile: type", {"text": value})
                        _hide_keyboard_safely(driver, platform)
                        data["result"] = "success"
                    except Exception:
                        data["result"] = f"can't find focused element after tapping bounds {bounds}"
                else:
                    data["result"] = f"can't find focused element in bounds {bounds}"

        elif data["action"] == "input" and "xpath" in data:
            xpath = data["xpath"]
            value = data["value"]
            elements = driver.find_elements(AppiumBy.XPATH, xpath)
            if not elements:
                data["result"] = f"can't find element {xpath}"
            else:
                field = elements[0]
                try:
                    field.click()
                except WebDriverException:
                    pass
                if _send_keys_safely(field, value, platform):
                    _hide_keyboard_safely(driver, platform)
                    data["result"] = "success"
                else:
                    fresh = _find_focused_element(driver, platform)
                    if fresh and _send_keys_safely(fresh, value, platform):
                        _hide_keyboard_safely(driver, platform)
                        data["result"] = "success"
                    else:
                        if platform == "ios":
                            try:
                                driver.execute_script("mobile: type", {"text": value})
                                _hide_keyboard_safely(driver, platform)
                                data["result"] = "success"
                            except Exception:
                                data["result"] = f"can't find focused element after clicking {xpath}"
                        else:
                            data["result"] = f"can't find focused element after clicking {xpath}"
        elif data["action"] == "navigate":
            url = data.get("url")
            if not url or not isinstance(url, str):
                data["result"] = "missing or invalid 'url' for navigate"
            else:
                try:
                    driver.get(url)
                    # tiny settle time for dynamic pages
                    sleep(0.5)
                    data["result"] = "success"
                except Exception as e:
                    data["result"] = f"navigate failed: {e}"

        elif data["action"] == "wait":
            sleep(data["timeout"] / 1000)
            data["result"] = "success"

        else:
            data["result"] = "unknown action"
            return None, None, json.dumps(data)

        return take_page_source(driver, folder, step_name), take_screenshot(driver, folder, step_name), json.dumps(data)
    except Exception as e:
        data["result"] = f"exception: {e}"
        return None, None, json.dumps(data)


# -----------------------------
# Misc helpers
# -----------------------------
def safe_json_loads(raw):
    """Return dict/list from a messy JSON-looking string (code fences, quotes, etc.)."""
    if isinstance(raw, (dict, list)) or raw is None:
        return raw

    s = str(raw).strip().lstrip("\ufeff")  # drop BOM if present

    # Drop one pair of wrapping quotes if present
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        s = s[1:-1].strip()

    # Remove Markdown code fences like ```json ... ```
    s = re.sub(r'^\s*```[a-zA-Z0-9_-]*\s*', '', s)
    s = re.sub(r'\s*```\s*$', '', s)
    s = s.strip()

    # If there’s leading chatter, cut to the first object/array
    starts = [p for p in (s.find('{'), s.find('[')) if p != -1]
    if starts:
        s = s[min(starts):]

    # First attempt: straight parse
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        # Fallback: clip to a balanced top-level {...} or [...]
        def clip_balanced(text):
            opens = {'{': '}', '[': ']'}
            if not text or text[0] not in opens:
                return text
            open_ch, close_ch = text[0], opens[text[0]]
            depth, in_str, esc = 0, False, False
            for i, ch in enumerate(text):
                if in_str:
                    if esc:
                        esc = False
                    elif ch == '\\':
                        esc = True
                    elif ch == '"':
                        in_str = False
                    continue
                if ch == '"':
                    in_str = True
                elif ch == open_ch:
                    depth += 1
                elif ch == close_ch:
                    depth -= 1
                    if depth == 0:
                        return text[:i+1]
            return text  # give up—let json.loads raise below

        clipped = clip_balanced(s)
        logger.info(f"!!!Clipped {clipped}")
        return json.loads(clipped)


def get_current_timestamp():
    now = datetime.datetime.now()
    return now.strftime("%Y-%m-%d-%H-%M-%S")


def keep_driver_live(driver: webdriver.Remote):
    try:
        while driver:
            _ = _safe_page_source(driver)
            sleep(10)
    except Exception:
        logger.debug("Driver keep-alive thread exiting")


def generate_summary_report(reports_folder: str, summary: List[dict]) -> str:
    """Save aggregated task results to ``summary.json``."""

    report_path = f"{reports_folder}/summary.json"
    return write_to_file(report_path, json.dumps(summary, indent=2))


def _run_tasks(
    prompt: str,
    tasks: List[Dict[str, Any]],
    server: Optional[str],
    platform: Optional[str],
    reports_folder: str,
    debug: bool = False,
    task_id: Optional[str] = None,
    llm_mode: Optional[str] = None,
    targets: Optional[List[Dict[str, Any]]] = None,
) -> RunResult:
    """Execute tasks using one or more automation targets."""

    create_folder(reports_folder)
    run_identifier = task_id or get_current_timestamp()
    target_contexts, default_target = _prepare_target_contexts(
        server, platform, targets
    )
    multi_target = len(target_contexts) > 1

    if multi_target:
        descriptor = ", ".join(
            f"{alias} ({ctx.platform}) via {ctx.server}" for alias, ctx in target_contexts.items()
        )
        logger.info(
            "Starting run %s with %d task(s) on targets: %s",
            run_identifier,
            len(tasks),
            descriptor,
        )
    else:
        alias, ctx = next(iter(target_contexts.items()))
        logger.info(
            "Starting run %s with %d task(s) on %s via %s",
            run_identifier,
            len(tasks),
            ctx.platform,
            ctx.server,
        )

    summary: List[dict] = []
    summary_path = ""

    available_targets_meta = {
        alias: {"platform": ctx.platform, "server": ctx.server}
        for alias, ctx in target_contexts.items()
    }

    try:
        for task in tasks:
            logger.debug("Task payload: %s", task)
            name = task["name"]
            details = task["details"]
            skip = task.get("skip", False)
            scope = task.get("scope", "functional")
            steps = task.get("steps")
            if skip:
                logger.info("Skipping task '%s'", name)
                continue

            reports_path = os.path.join(reports_folder, name, run_identifier)
            task_folder = create_folder(reports_path)
            write_to_file(f"{task_folder}/task.json", json.dumps(task))
            sleep(1)

            effective_llm_mode = _resolve_task_llm_mode(llm_mode, task)
            logger.debug(
                "Using '%s' mode for task '%s'", effective_llm_mode, task.get("name")
            )

            target_states: Dict[str, Dict[str, Optional[str]]] = {}
            for alias, ctx in target_contexts.items():
                page_name = _step_page_name(0, alias, multi_target)
                screenshot_name = _step_screenshot_name(0, alias, multi_target)
                page_path = take_page_source(ctx.driver, task_folder, page_name)
                screenshot_path = take_screenshot(ctx.driver, task_folder, screenshot_name)
                description = (
                    _describe_screenshot_with_vision_model(screenshot_path)
                    if effective_llm_mode == "vision" and screenshot_path
                    else None
                )
                target_states[alias] = {
                    "page": page_path,
                    "screenshot": screenshot_path,
                    "description": description,
                }

            history_actions: List[str] = []
            step = 0
            current_target, selection_error = _choose_target_alias(
                target_contexts,
                task.get("target") or task.get("default_target"),
                task.get("platform"),
                default_target,
            )
            if selection_error:
                logger.warning(
                    "Task '%s' requested %s; defaulting to '%s'",
                    name,
                    selection_error,
                    current_target,
                )

            task_result = {
                "name": name,
                "scope": scope,
                "steps": [],
                "reports_path": os.path.normpath(reports_path).replace("\\", "/"),
                "task_id": run_identifier,
            }

            if steps:
                for raw_step in steps:
                    step += 1
                    step_action = dict(raw_step)
                    desired_alias = (
                        step_action.get("target")
                        or step_action.get("device")
                        or step_action.get("session")
                    )
                    platform_hint = (
                        step_action.get("platform")
                        or step_action.get("platformName")
                        or step_action.get("platform_name")
                    )
                    target_alias, alias_error = _choose_target_alias(
                        target_contexts,
                        desired_alias,
                        platform_hint,
                        current_target,
                    )
                    step_action.setdefault("target", target_alias)
                    step_action.setdefault(
                        "platform", target_contexts[target_alias].platform
                    )
                    if alias_error:
                        step_action["result"] = alias_error
                        serialised = json.dumps(step_action)
                        write_to_file(f"{task_folder}/step{step}.json", serialised)
                        task_result["steps"].append(json.loads(serialised))
                        current_target = target_alias
                        continue

                    artifact_name = _step_page_name(step, target_alias, multi_target)
                    (
                        page_path,
                        screenshot_path,
                        next_action_with_result,
                    ) = process_next_action(
                        step_action,
                        target_contexts[target_alias].driver,
                        task_folder,
                        artifact_name,
                    )
                    write_to_file(
                        f"{task_folder}/step{step}.json",
                        next_action_with_result,
                    )
                    task_result["steps"].append(json.loads(next_action_with_result))

                    state = target_states.setdefault(
                        target_alias, {"page": None, "screenshot": None, "description": None}
                    )
                    state["page"] = page_path
                    state["screenshot"] = screenshot_path
                    if effective_llm_mode == "vision" and screenshot_path:
                        state["description"] = _describe_screenshot_with_vision_model(
                            screenshot_path
                        )
                    current_target = target_alias
            else:
                while True:
                    current_state = target_states.get(current_target)
                    page_source_for_next_step = (
                        current_state.get("page") if current_state else None
                    )
                    if page_source_for_next_step is None:
                        break

                    page_source = read_file_content(page_source_for_next_step) or ""
                    history_actions_str = "\n".join(history_actions)
                    screen_description = (
                        current_state.get("description") if current_state else None
                    )
                    screenshot_for_next_step = (
                        current_state.get("screenshot") if current_state else None
                    )
                    prompts = [
                        f"# Task \n {details}",
                        f"# History of Actions \n {history_actions_str}",
                        f"# Source of Page \n ```yaml\n {page_source} \n```",
                    ]
                    if screen_description:
                        prompts.append(f"# Screen Description \n {screen_description}")
                    write_to_file(
                        f"{task_folder}/step{step + 1}_prompt.md",
                        "\n".join(prompts),
                    )

                    if debug:
                        next_action_raw = input("next action:")
                    else:
                        next_action_raw = generate_next_action(
                            prompt,
                            details,
                            history_actions,
                            page_source_for_next_step,
                            screenshot_for_next_step,
                            effective_llm_mode,
                            screen_description=screen_description,
                            available_targets=available_targets_meta,
                            active_target=current_target,
                        )

                    logger.debug("Step %s: %s", step + 1, next_action_raw)

                    parsed_action = safe_json_loads(next_action_raw)
                    if not isinstance(parsed_action, dict):
                        parsed_action = {
                            "action": "error",
                            "result": "invalid action format",
                        }

                    desired_alias = (
                        parsed_action.get("target")
                        or parsed_action.get("device")
                        or parsed_action.get("session")
                    )
                    platform_hint = (
                        parsed_action.get("platform")
                        or parsed_action.get("platformName")
                        or parsed_action.get("platform_name")
                    )
                    target_alias, alias_error = _choose_target_alias(
                        target_contexts,
                        desired_alias,
                        platform_hint,
                        current_target,
                    )
                    parsed_action["target"] = target_alias
                    parsed_action.setdefault(
                        "platform", target_contexts[target_alias].platform
                    )

                    step += 1

                    if alias_error:
                        parsed_action["result"] = alias_error
                        serialised = json.dumps(parsed_action)
                        write_to_file(f"{task_folder}/step{step}.json", serialised)
                        history_actions.append(serialised)
                        task_result["steps"].append(json.loads(serialised))
                        current_target = target_alias
                        break

                    artifact_name = _step_page_name(step, target_alias, multi_target)
                    (
                        page_path,
                        screenshot_path,
                        next_action_with_result,
                    ) = process_next_action(
                        parsed_action,
                        target_contexts[target_alias].driver,
                        task_folder,
                        artifact_name,
                    )
                    write_to_file(
                        f"{task_folder}/step{step}.json",
                        next_action_with_result,
                    )
                    history_actions.append(next_action_with_result)
                    task_result["steps"].append(json.loads(next_action_with_result))

                    state = target_states.setdefault(
                        target_alias, {"page": None, "screenshot": None, "description": None}
                    )
                    state["page"] = page_path
                    state["screenshot"] = screenshot_path
                    if effective_llm_mode == "vision" and screenshot_path:
                        state["description"] = _describe_screenshot_with_vision_model(
                            screenshot_path
                        )
                    elif page_path is None:
                        state["description"] = None

                    current_target = target_alias

                    action_type = parsed_action.get("action")
                    if action_type in {"finish", "error"}:
                        break
                    if page_path is None:
                        break

            summary.append(task_result)

        if summary:
            summary_folder = os.path.join(
                reports_folder, summary[0]["name"], run_identifier
            )
            summary_path = generate_summary_report(summary_folder, summary)
    finally:
        for ctx in target_contexts.values():
            try:
                ctx.driver.quit()
            except Exception:
                pass
        logger.info("Finished run %s", run_identifier)

    return RunResult(summary=summary, summary_path=summary_path)


def run_tasks(
    prompt: str,
    tasks: List[Dict[str, Any]],
    server: Optional[str],
    platform: Optional[str],
    reports_folder: str,
    debug: bool = False,
    task_id: Optional[str] = None,
    llm_mode: Optional[str] = None,
    targets: Optional[List[Dict[str, Any]]] = None,
) -> RunResult:
    """Run tasks synchronously (backwards compatible helper)."""

    return _run_tasks(
        prompt,
        tasks,
        server,
        platform,
        reports_folder,
        debug,
        task_id=task_id,
        llm_mode=llm_mode,
        targets=targets,
    )


async def run_tasks_async(
    prompt: str,
    tasks: List[Dict[str, Any]],
    server: Optional[str],
    platform: Optional[str],
    reports_folder: str,
    debug: bool = False,
    task_id: Optional[str] = None,
    llm_mode: Optional[str] = None,
    targets: Optional[List[Dict[str, Any]]] = None,
) -> RunResult:
    """Run tasks in a shared background executor for concurrency."""

    loop = asyncio.get_running_loop()
    executor = _get_executor()
    func = partial(
        _run_tasks,
        prompt,
        tasks,
        server,
        platform,
        reports_folder,
        debug,
        task_id,
        llm_mode,
        targets,
    )
    return await loop.run_in_executor(executor, func)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Testing Tool")
    parser.add_argument("prompt", help="Prompt file")
    parser.add_argument("task", help="Task file")
    parser.add_argument(
        "--appium",
        default="http://localhost:4723",
        help="Appium server, default is localhost:4723",
    )
    parser.add_argument(
        "--platform",
        choices=["android", "ios", "web"],
        default="android",
        help="Target platform for testing",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug mode, default is false")
    parser.add_argument(
        "--reports", default="./reports", help="Folder to store the reports, default is ./reports"
    )
    parser.add_argument(
        "--llm-mode",
        choices=sorted(_LLM_MODES),
        default="auto",
        help="Preferred LLM mode: auto, text, or vision",
    )

    args = parser.parse_args()

    prompt_file = args.prompt
    task_file = args.task
    debug = args.debug
    platform = args.platform
    reports_folder = args.reports
    appium_server = args.appium
    llm_mode = args.llm_mode

    prompt = read_file_content(prompt_file)
    tasks = json.loads(read_file_content(task_file))

    driver = create_driver(appium_server, platform)
    driver.implicitly_wait(0.2)
    thread = threading.Thread(target=lambda: keep_driver_live(driver), daemon=True)
    thread.start()

    for i, task in enumerate(tasks):
        logger.debug("Task payload: %s", task)
        name = task.get("name", f"task_{i+1}")
        details = task.get("details", "")
        skip = task.get("skip", False)
        apps = task.get("apps") or []  # <---- per-task app activation order
        if skip:
            logger.info("Skipping task '%s'", name)
            continue

        task_folder = create_folder(f"{reports_folder}/{name}/{get_current_timestamp()}")
        write_to_file(f"{task_folder}/task.json", json.dumps(task, ensure_ascii=False, indent=2))
        sleep(0.5)

        # Activate any declared apps for this task, in order
        activate_sequence_for_task(driver, platform, apps)

        page_source_for_next_step = take_page_source(driver, task_folder, "step_0")
        page_screenshot_for_next_step = take_screenshot(
            driver, task_folder, "step_0"
        )
        history_actions: List[str] = []
        step = 0
        effective_llm_mode = _resolve_task_llm_mode(llm_mode, task)
        logger.debug(
            "CLI run using '%s' mode for task '%s'",
            effective_llm_mode,
            task.get("name"),
        )

        while page_source_for_next_step is not None:
            step += 1
            page_source = read_file_content(page_source_for_next_step)
            history_actions_str = "\\n".join(history_actions)
            screen_description = None
            if effective_llm_mode == "vision" and page_screenshot_for_next_step:
                screen_description = _describe_screenshot_with_vision_model(
                    page_screenshot_for_next_step
                )
            prompts = [
                f"# Task \\n {details}",
                f"# History of Actions \\n {history_actions_str}",
                f"# Source of Page \\n ```yaml\\n {page_source} \\n```",
            ]
            if screen_description:
                prompts.append(f"# Screen Description \\n {screen_description}")
            write_to_file(f"{task_folder}/step_{step}_prompt.md", "\\n".join(prompts))

            if debug:
                next_action = input("next action:")
            else:
                next_action = generate_next_action(
                    prompt,
                    details,
                    history_actions,
                    page_source_for_next_step,
                    page_screenshot_for_next_step,
                    effective_llm_mode,
                    screen_description=screen_description,
                )

            logger.debug("Step %s: %s", step, next_action)

            (
                page_source_for_next_step,
                page_screenshot_for_next_step,
                next_action_with_result,
            ) = process_next_action(
                next_action, driver, task_folder, f"step_{step}"
            )

            write_to_file(f"{task_folder}/step_{step}.json", next_action_with_result)
            history_actions.append(next_action_with_result)

        # Quit driver after last task
        if i == len(tasks) - 1:
            try:
                driver.quit()
            finally:
                driver = None