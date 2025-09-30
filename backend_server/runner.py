import argparse
import datetime
import json
import os
import threading
from typing import Optional, Dict, Any, List

from openai import OpenAI

import base64
from time import sleep
from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.options.ios import XCUITestOptions
from appium.webdriver.common.appiumby import AppiumBy
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont
from html.parser import HTMLParser
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
from dotenv import load_doten

from libraries.taas.dhub import Dhub

load_dotenv()


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
        print(f"Error: The file '{file_path}' does not exist.")
    except IOError:
        print(f"Error: Unable to read the file '{file_path}'.")

def create_folder(folder_path):
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
    return folder_path


def image_to_base64(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


# -----------------------------
# LLM: next action generation
# -----------------------------
def generate_next_action(_prompt, _task, _history_actions, page_source_file):
    _page_src = read_file_content(page_source_file)
    _history_actions_str = "\\n".join(_history_actions)
    _messages = []
    _messages.append({"role": "system", "content": _prompt})
    _messages.append(
        {
            "role": "user",
            "content": [
                {"type": "text", "text": f"# Task \\n {_task}"},
                {"type": "text", "text": f"# History of Actions \\n {_history_actions_str}"},
                {"type": "text", "text": f"# Source of Page \\n ```yaml\\n {_page_src} \\n```"},
            ],
        }
    )

    open_ai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"),
                     base_url=os.getenv("OPENAI_BASE_URL"))
    chat_response = open_ai.chat.completions.create(
        model=os.getenv("OPENAI_MODEL"), messages=_messages
    )
    content = chat_response.choices[0].message.content
    return content


# -------------------------------------------------------
# Drivers (multi-app friendly)
# -------------------------------------------------------
def create_driver(_server, _platform="android",
                  extra_caps: Optional[Dict[str, Any]] = None):
    extra_caps = extra_caps or {}

    if _platform.lower() == "android":
        capabilities = {
            "platformName": "Android",
            "automationName": "uiautomator2",
            "deviceName": "google_api",
            "language": "en",
            "locale": "US",
            "appium:newCommandTimeout": 0,
            "appium:uiautomator2ServerLaunchTimeout": 0,
            # optional: set appPackage/appActivity if you want to auto-launch
            # "appium:appPackage": "com.fortinet.android.ftm",
            # "appium:appActivity": "com.fortinet.android.ftm.MainActivity",
            "appium:noReset": True,
            }
        capabilities.update(extra_caps)
        return webdriver.Remote(
            _server,
            options=UiAutomator2Options().load_capabilities(capabilities),
            )

    if _platform.lower() == "ios":
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
        return webdriver.Remote(
            _server,
            options=XCUITestOptions().load_capabilities(capabilities)
            )

    if _platform.lower() == "web":
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
            print(f"check status {status}")
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


# -----------------------------
# Actions processing
# -----------------------------
def parse_bounds(bounds):
    left_top, right_bottom = bounds.split("][")
    left, top = map(int, left_top[1:].split(","))
    right, bottom = map(int, right_bottom[:-1].split(","))
    return (left, top, right, bottom)

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
            print(f"[activate] {bundle_or_pkg}: {e}")


def process_next_action(action, driver: webdriver.Remote, folder, step_name):
    data = json.loads(action)
    platform = _get_platform(driver)
    if data["action"] in ("error", "finish"):
        take_page_source(driver, folder, step_name)
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

        return take_page_source(driver, folder, step_name), None, json.dumps(data)
    except Exception as e:
        data["result"] = f"exception: {e}"
        return None, None, json.dumps(data)


# -----------------------------
# Misc helpers
# -----------------------------
def get_current_timestamp():
    now = datetime.datetime.now()
    return now.strftime("%Y-%m-%d-%H-%M-%S")


def keep_driver_live(driver: webdriver.Remote):
    try:
        while driver:
            _ = _safe_page_source(driver)
            sleep(10)
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
            print(f"[activate] {bundle_or_pkg}: {e}")


def process_next_action(action, driver: webdriver.Remote, folder, step_name):
    data = json.loads(action)
    platform = _get_platform(driver)
    if data["action"] in ("error", "finish"):
        take_page_source(driver, folder, step_name)
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

        return take_page_source(driver, folder, step_name), None, json.dumps(data)
    except Exception as e:
        data["result"] = f"exception: {e}"
        return None, None, json.dumps(data)


# -----------------------------
# Misc helpers
# -----------------------------
def get_current_timestamp():
    now = datetime.datetime.now()
    return now.strftime("%Y-%m-%d-%H-%M-%S")


def keep_driver_live(driver: webdriver.Remote):
    try:
        while driver:
            _ = _safe_page_source(driver)
            sleep(10)
    except Exception:
        print("closing thread.")


# -----------------------------
# Main
# -----------------------------
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

    args = parser.parse_args()

    prompt_file = args.prompt
    task_file = args.task
    debug = args.debug
    platform = args.platform
    reports_folder = args.reports
    appium_server = args.appium

    prompt = read_file_content(prompt_file)
    tasks = json.loads(read_file_content(task_file))

    driver = create_driver(appium_server, platform)
    driver.implicitly_wait(0.2)
    thread = threading.Thread(target=lambda: keep_driver_live(driver), daemon=True)
    thread.start()

    for i, task in enumerate(tasks):
        print(task)
        name = task.get("name", f"task_{i+1}")
        details = task.get("details", "")
        skip = task.get("skip", False)
        apps = task.get("apps") or []  # <---- per-task app activation order
        if skip:
            print(f"skip {name}")
            continue

        task_folder = create_folder(f"{reports_folder}/{name}/{get_current_timestamp()}")
        write_to_file(f"{task_folder}/task.json", json.dumps(task, ensure_ascii=False, indent=2))
        sleep(0.5)

        # Activate any declared apps for this task, in order
        activate_sequence_for_task(driver, platform, apps)

        page_source_for_next_step = take_page_source(driver, task_folder, "step_0")
        history_actions: List[str] = []
        step = 0

        while page_source_for_next_step is not None:
            step += 1
            page_source = read_file_content(page_source_for_next_step)
            history_actions_str = "\\n".join(history_actions)
            prompts = [
                f"# Task \\n {details}",
                f"# History of Actions \\n {history_actions_str}",
                f"# Source of Page \\n ```yaml\\n {page_source} \\n```",
            ]
            write_to_file(f"{task_folder}/step_{step}_prompt.md", "\\n".join(prompts))

            if debug:
                next_action = input("next action:")
            else:
                next_action = generate_next_action(
                    prompt,
                    details,
                    history_actions,
                    page_source_for_next_step
                )

            print(f"{step}: {next_action}")

            (page_source_for_next_step,
                _page_screenshot_for_next_step,
                next_action_with_result) = process_next_action(next_action, driver, task_folder, f"step_{step}")

            write_to_file(f"{task_folder}/step_{step}.json", next_action_with_result)
            history_actions.append(next_action_with_result)

        # Quit driver after last task
        if i == len(tasks) - 1:
            try:
                driver.quit()
            finally:
                driver = None
