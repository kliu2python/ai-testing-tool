"""Utility functions for running AI-driven UI automation tasks."""

from __future__ import annotations

import argparse
import base64
import datetime
import json
import os
import threading
from dataclasses import dataclass
from time import sleep
from typing import Any, Dict, List, Optional, Tuple

from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.options.ios import XCUITestOptions
from appium.webdriver.common.appiumby import AppiumBy
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont
from selenium import webdriver as selenium_webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
import xml.etree.ElementTree as ET
import yaml


@dataclass
class RunResult:
    """Container for aggregated run results."""

    summary: List[Dict[str, Any]]
    summary_path: str


def read_file_content(file_path: str) -> Optional[str]:
    """Return the content of ``file_path`` if it exists."""

    try:
        with open(file_path, "r", encoding="utf-8") as file:
            content = file.read()
        return content
    except FileNotFoundError:
        print(f"Error: The file '{file_path}' does not exist.")
    except IOError:
        print(f"Error: Unable to read the file '{file_path}'.")
    return None


def create_folder(folder_path: str) -> str:
    """Create ``folder_path`` if missing and return the path."""

    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
    return folder_path


def image_to_base64(image_path: str) -> str:
    """Convert an image file to a base64-encoded string."""

    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def generate_next_action(
    prompt: str,
    task: str,
    history_actions: List[str],
    page_source_file: str,
    page_screenshot: str,
) -> str:
    """Ask the LLM for the next UI action to execute."""

    screenshot_base64 = image_to_base64(page_screenshot)
    page_source = read_file_content(page_source_file) or ""
    history_actions_str = "\n".join(history_actions)
    messages: List[Any] = []
    messages.append({"role": "system", "content": prompt})
    messages.append(
        {
            "role": "user",
            "content": [
                {"type": "text", "text": f"# Task \n {task}"},
                {
                    "type": "text",
                    "text": f"# History of Actions \n {history_actions_str}",
                },
                {
                    "type": "text",
                    "text": f"# Source of Page \n ```yaml\n {page_source} \n```",
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{screenshot_base64}"
                    },
                },
            ],
        }
    )

    openAI = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    chat_response = openAI.chat.completions.create(
        model="gpt-4-turbo", messages=messages, max_tokens=200
    )

    content = chat_response.choices[0].message.content
    return content


def create_driver(server: str, platform: str) -> Any:
    """Create a webdriver for the desired platform."""

    if platform == "android":
        capabilities = dict(
            platformName="Android",
            automationName="uiautomator2",
            deviceName="Android",
            language="en",
            locale="US",
        )
        return webdriver.Remote(
            server,
            options=UiAutomator2Options().load_capabilities(capabilities),
        )
    if platform == "ios":
        capabilities = dict(
            platformName="iOS", automationName="XCUITest", deviceName="iPhone"
        )
        return webdriver.Remote(
            server, options=XCUITestOptions().load_capabilities(capabilities)
        )
    if platform == "web":
        chrome_options = ChromeOptions()
        return selenium_webdriver.Remote(
            command_executor=server, options=chrome_options
        )
    raise ValueError(f"Unsupported platform: {platform}")


def resize_image(
    img: Image.Image, max_long: int = 2048, max_short: int = 768
) -> Image.Image:
    """Resize ``img`` while maintaining the aspect ratio."""

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


def draw_grid_with_labels(
    image_path: str, grid_size: int, output_path: str
) -> None:
    """Overlay a coordinate grid on ``image_path`` and save to ``output_path``."""

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
            draw.text(
                (x - 5, 5),
                str((x - label_space) // grid_size),
                fill="black",
                font=font,
            )

        for y in range(label_space, new_height, grid_size):
            line = ((label_space, y), (new_width, y))
            draw.line(line, fill=128)
            draw.text(
                (5, y - 10),
                str((y - label_space) // grid_size),
                fill="black",
                font=font,
            )

        resize_image(new_img).save(output_path)


def format_image(image_path: str, output_path: str) -> None:
    """Convert an image with alpha channel to RGB format."""

    with Image.open(image_path) as img:
        width, height = img.size

        new_img = Image.new("RGB", (width, height), "white")
        new_img.paste(img)

        resize_image(new_img).save(output_path)


def write_to_file(file_path: str, string_to_write: str) -> str:
    """Write ``string_to_write`` to ``file_path`` and return the path."""

    with open(file_path, "w", encoding="utf-8") as file:
        file.write(string_to_write)
    return file_path


def write_to_file_with_line_filter(
    file_path: str, string_to_write: str, filter: str
) -> str:
    """Write only lines containing ``filter`` to ``file_path``."""

    filtered_lines = [
        line.strip() for line in string_to_write.split("\n") if filter in line
    ]
    with open(file_path, "w", encoding="utf-8") as file:
        file.write("\n".join(filtered_lines))
    return file_path


def remove_unexpected_attr(node: ET.Element) -> None:
    """Strip attributes other than a predefined whitelist from ``node``."""

    unexpected_keys = [
        key
        for key, value in node.attrib.items()
        if key
        not in [
            "index",
            "package",
            "class",
            "text",
            "resource-id",
            "content-desc",
            "clickable",
            "scrollable",
            "bounds",
        ]
    ]
    for key in unexpected_keys:
        del node.attrib[key]
    for child in node:
        remove_unexpected_attr(child)


def refine_xml(xml_str: str) -> str:
    """Return a refined XML string containing only whitelisted attributes."""

    root = ET.fromstring(xml_str)
    remove_unexpected_attr(root)
    return ET.tostring(root, encoding="unicode")


def xml_to_dict(xml_element: ET.Element) -> dict:
    """Convert an XML element tree into a nested dictionary."""

    result: Dict[str, Any] = {}
    for child in xml_element:
        child_dict = xml_to_dict(child)
        if child_dict:
            if child.tag in result and result[child.tag]:
                result[child.tag].append(child_dict)
            else:
                result[child.tag] = [child_dict]

    if xml_element.text and xml_element.text.strip():
        text = xml_element.text.strip()
        if "content" in result and result["content"]:
            result["content"].append(text)
        else:
            result["content"] = [text]

    expected_attrib = {
        (key, value)
        for key, value in xml_element.attrib.items()
        if key
        in [
            "index",
            "package",
            "class",
            "text",
            "resource-id",
            "content-desc",
            "clickable",
            "scrollable",
            "bounds",
        ]
        and value.strip()
    }
    if expected_attrib:
        result.update(expected_attrib)
    return result


def xml_to_yaml(xml_file: str, yaml_file: str) -> str:
    """Convert an XML file into a YAML file."""

    root = ET.fromstring(read_file_content(xml_file) or "")
    xml_dict = xml_to_dict(root)
    yaml_data = yaml.dump(xml_dict, default_flow_style=False)
    return write_to_file(yaml_file, yaml_data)


def xml_str_to_yaml(yaml_file: str, xml_str: str) -> str:
    """Convert an XML string into YAML and save to ``yaml_file``."""

    root = ET.fromstring(xml_str)
    xml_dict = xml_to_dict(root)
    yaml_data = yaml.dump(xml_dict, default_flow_style=False)
    return write_to_file(yaml_file, yaml_data)


def take_page_source(driver: Any, folder: str, name: str) -> str:
    """Save page source to XML and YAML files and return YAML path."""

    write_to_file(f"{folder}/{name}.xml", driver.page_source)
    return xml_str_to_yaml(f"{folder}/{name}.yaml", driver.page_source)


def take_screenshot(driver: Any, folder: str, name: str) -> str:
    """Capture a screenshot and convert it to JPEG."""

    driver.save_screenshot(f"{folder}/{name}.png")
    format_image(f"{folder}/{name}.png", f"{folder}/{name}.jpg")
    return f"{folder}/{name}.jpg"


def parse_bounds(bounds: str) -> Tuple[int, int, int, int]:
    """Parse a UI element bounds string into coordinates."""

    left_top, right_bottom = bounds.split("][")
    left, top = map(int, left_top[1:].split(","))
    right, bottom = map(int, right_bottom[:-1].split(","))
    return (left, top, right, bottom)


def process_next_action(
    action: str, driver: Any, folder: str, step_name: str
) -> Tuple[Optional[str], Optional[str], str]:
    """Execute the JSON ``action`` and return artifacts paths."""

    data = json.loads(action)

    if data["action"] == "error" or data["action"] == "finish":
        take_page_source(driver, folder, step_name),
        take_screenshot(driver, folder, step_name),
        data["result"] = "success"
        return (None, None, json.dumps(data))
    if data["action"] == "tap" and "bounds" in data:
        bounds = data["bounds"]
        left, top, right, bottom = parse_bounds(bounds)
        tap_x = left + (right - left) / 2
        tap_y = top + (bottom - top) / 2
        driver.tap([(tap_x, tap_y)])
        data["result"] = "success"
    elif data["action"] == "tap" and "xpath" in data:
        xpath = data["xpath"]
        elements = driver.find_elements(by=AppiumBy.XPATH, value=xpath)
        if elements:
            elements[0].click()
            data["result"] = "success"
        else:
            data["result"] = f"can't find element {xpath}"
            print(f"Can't find element {xpath}")
    elif data["action"] == "swipe":
        swipe_start_x = data["swipe_start_x"]
        swipe_start_y = data["swipe_start_y"]
        swipe_end_x = data["swipe_end_x"]
        swipe_end_y = data["swipe_end_y"]
        duration = data["duration"]
        driver.swipe(
            swipe_start_x, swipe_start_y, swipe_end_x, swipe_end_y, duration
        )
        sleep(duration / 1000)
        data["result"] = "success"
    elif data["action"] == "input" and "bounds" in data:
        bounds = data["bounds"]
        value = data["value"]
        left, top, right, bottom = parse_bounds(bounds)
        tap_x = left + (right - left) / 2
        tap_y = top + (bottom - top) / 2
        driver.tap([(tap_x, tap_y)])
        elements = driver.find_elements(
            by=AppiumBy.XPATH, value="//*[@focused='true']"
        )
        if elements:
            elements[0].send_keys(value)
            driver.hide_keyboard()
            data["result"] = "success"
        else:
            data["result"] = f"can't find element in bounds {bounds}"
            print(f"Can't find element in bounds {bounds}")
    elif data["action"] == "input" and "xpath" in data:
        xpath = data["xpath"]
        value = data["value"]
        elements = driver.find_elements(by=AppiumBy.XPATH, value=xpath)
        if elements:
            elements[0].click()
            fresh_element = driver.find_element(
                by=AppiumBy.XPATH, value="//*[@focused='true']"
            )
            fresh_element.send_keys(value)
            driver.hide_keyboard()
            data["result"] = "success"
        else:
            data["result"] = f"can't find element {xpath}"
            print(f"Can't find element {xpath}")
    elif data["action"] == "wait":
        sleep(data["timeout"] / 1000)
        data["result"] = "success"
    else:
        print(f"unknown action, {action}")
        data["result"] = "unknown action"
        return (None, None, json.dumps(data))

    return (
        take_page_source(driver, folder, step_name),
        take_screenshot(driver, folder, step_name),
        json.dumps(data),
    )


def get_current_timestamp() -> str:
    """Return the current timestamp as a string."""

    now = datetime.datetime.now()
    timestamp_str = now.strftime("%Y-%m-%d-%H-%M-%S")
    return timestamp_str


def keep_driver_live(driver: Any) -> None:
    """Keep the driver session alive in a background thread."""

    try:
        while driver:
            driver.page_source
            sleep(10)
    except Exception:
        print("closing thread.")


def generate_summary_report(reports_folder: str, summary: List[dict]) -> str:
    """Save aggregated task results to ``summary.json``."""

    report_path = f"{reports_folder}/summary.json"
    return write_to_file(report_path, json.dumps(summary, indent=2))


def run_tasks(
    prompt: str,
    tasks: List[Dict[str, Any]],
    server: str,
    platform: str,
    reports_folder: str,
    debug: bool = False,
) -> RunResult:
    """Execute tasks using the configured automation server."""

    create_folder(reports_folder)
    driver = create_driver(server, platform)
    driver.implicitly_wait(0.2)
    thread = threading.Thread(
        target=lambda: keep_driver_live(driver), daemon=True
    )
    thread.start()

    summary: List[dict] = []
    summary_path = ""

    try:
        for task in tasks:
            print(task)
            name = task["name"]
            details = task["details"]
            skip = task.get("skip", False)
            scope = task.get("scope", "functional")
            steps = task.get("steps")
            if skip:
                print(f"skip {name}")
                continue

            task_folder = create_folder(
                f"{reports_folder}/{name}/{get_current_timestamp()}"
            )
            write_to_file(f"{task_folder}/task.json", json.dumps(task))
            sleep(1)
            page_source_for_next_step = take_page_source(
                driver, task_folder, "step_0"
            )
            page_screenshot_for_next_step = take_screenshot(
                driver, task_folder, "step_0"
            )
            history_actions: List[str] = []
            step = 0
            task_result = {"name": name, "scope": scope, "steps": []}

            if steps:
                for step_action in steps:
                    step += 1
                    next_action = json.dumps(step_action)
                    (
                        page_source_for_next_step,
                        page_screenshot_for_next_step,
                        next_action_with_result,
                    ) = process_next_action(
                        next_action, driver, task_folder, f"step_{step}"
                    )
                    write_to_file(
                        f"{task_folder}/step_{step}.json",
                        next_action_with_result,
                    )
                    task_result["steps"].append(
                        json.loads(next_action_with_result)
                    )
            else:
                while page_source_for_next_step is not None:
                    step += 1
                    page_source = (
                        read_file_content(page_source_for_next_step) or ""
                    )
                    history_actions_str = "\n".join(history_actions)
                    prompts = [
                        f"# Task \n {details}",
                        f"# History of Actions \n {history_actions_str}",
                        f"# Source of Page \n ```yaml\n {page_source} \n```",
                    ]
                    write_to_file(
                        f"{task_folder}/step_{step}_prompt.md",
                        "\n".join(prompts),
                    )

                    if debug:
                        next_action = input("next action:")
                    else:
                        next_action = generate_next_action(
                            prompt,
                            details,
                            history_actions,
                            page_source_for_next_step,
                            page_screenshot_for_next_step,
                        )

                    print(f"{step}: {next_action}")

                    (
                        page_source_for_next_step,
                        page_screenshot_for_next_step,
                        next_action_with_result,
                    ) = process_next_action(
                        next_action, driver, task_folder, f"step_{step}"
                    )
                    write_to_file(
                        f"{task_folder}/step_{step}.json",
                        next_action_with_result,
                    )
                    history_actions.append(next_action_with_result)
                    task_result["steps"].append(
                        json.loads(next_action_with_result)
                    )

            summary.append(task_result)

        summary_path = generate_summary_report(reports_folder, summary)
    finally:
        driver.quit()

    return RunResult(summary=summary, summary_path=summary_path)


def main() -> None:
    """Command line entry point for the AI testing tool."""

    parser = argparse.ArgumentParser(description="AI Testing Tool")
    parser.add_argument("prompt", help="Prompt file")
    parser.add_argument("task", help="Task file")
    parser.add_argument(
        "--server",
        default="http://localhost:4723",
        help="Automation server address, default is http://localhost:4723",
    )
    parser.add_argument(
        "--platform",
        choices=["android", "ios", "web"],
        default="android",
        help="Target platform for testing",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode, default is false",
    )
    parser.add_argument(
        "--reports",
        default="./reports",
        help="Folder to store the reports, default is ./reports",
    )

    args = parser.parse_args()

    prompt_file = args.prompt
    task_file = args.task
    debug = args.debug
    reports_folder = args.reports
    server = args.server
    platform = args.platform

    prompt = read_file_content(prompt_file) or ""
    tasks = json.loads(read_file_content(task_file) or "[]")

    run_tasks(prompt, tasks, server, platform, reports_folder, debug)


if __name__ == "__main__":
    main()
