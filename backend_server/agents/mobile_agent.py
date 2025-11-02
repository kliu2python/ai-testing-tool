"""Mobile automation agent that interacts with the existing runner."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable, List, Optional

from backend_server.runner import RunResult, run_tasks_async

from .data_models import CustomerIssue, TestOutcome, TestStatus

logger = logging.getLogger(__name__)


@dataclass
class DeviceDescriptor:
    """Representation of a device exposed by the mobile proxy."""

    name: str
    platform: str
    server: str
    os_version: Optional[str] = None
    model: Optional[str] = None

    def matches(self, platform: Optional[str], os_version: Optional[str]) -> bool:
        if platform and self.platform.lower() != platform.lower():
            return False
        if os_version and self.os_version:
            return self.os_version.lower().startswith(os_version.lower())
        return True


class MobileProxyClient:
    """Very small abstraction over the device pool."""

    def __init__(self, devices: Iterable[DeviceDescriptor]):
        self.devices: List[DeviceDescriptor] = list(devices)

    def allocate(self, platform: Optional[str], os_version: Optional[str]) -> Optional[DeviceDescriptor]:
        """Select the first available device matching the requirement."""

        for device in self.devices:
            if device.matches(platform, os_version):
                return device
        return None


class MobileAutomationRunner:
    """Wrapper around ``run_tasks_async`` that encapsulates prompts and reports."""

    def __init__(self, system_prompt: str, reports_folder: str = "./reports") -> None:
        self.system_prompt = system_prompt
        self.reports_folder = reports_folder

    async def run(
        self,
        tasks: List[dict],
        device: DeviceDescriptor,
        llm_mode: Optional[str] = None,
    ) -> RunResult:
        targets = [
            {
                "name": device.name,
                "platform": device.platform,
                "server": device.server,
                "default": True,
            }
        ]
        return await run_tasks_async(
            prompt=self.system_prompt,
            tasks=tasks,
            server=None,
            platform=None,
            reports_folder=self.reports_folder,
            targets=targets,
            llm_mode=llm_mode,
        )


class MobileTestAgent:
    """Agent that translates the issue into executable automation."""

    def __init__(
        self,
        proxy_client: MobileProxyClient,
        automation_runner: MobileAutomationRunner,
        llm_mode: Optional[str] = None,
    ) -> None:
        self.proxy_client = proxy_client
        self.automation_runner = automation_runner
        self.llm_mode = llm_mode

    async def execute(self, issue: CustomerIssue) -> TestOutcome:
        device = self.proxy_client.allocate(issue.platform, issue.os_version)
        if not device:
            details = (
                "No device matched the requested platform/OS version."
                if issue.platform
                else "Device platform information was not provided."
            )
            return TestOutcome(
                status=TestStatus.MISSING_INFORMATION,
                details=details,
                missing_information=["platform", "os_version"],
            )

        tasks = self._build_tasks(issue, device)
        logger.info(
            "Triggering automation on %s (%s) with %d task(s)",
            device.name,
            device.platform,
            len(tasks),
        )

        run_result = await self.automation_runner.run(tasks, device, llm_mode=self.llm_mode)
        return self._interpret_run_result(issue, run_result)

    def _build_tasks(self, issue: CustomerIssue, device: DeviceDescriptor) -> List[dict]:
        steps_text = "\n".join(f"{idx + 1}. {step}" for idx, step in enumerate(issue.steps)) or "None"
        expectation = issue.expected_result or "Customer did not provide"
        actual = issue.actual_result or "Customer did not provide"
        device_hint = f"Device under test: {device.name} ({device.platform} {device.os_version or 'unspecified'})"

        task_details = (
            f"Follow the customer's steps in the {device.platform} app to reproduce the issue.\n"
            f"{device_hint}\n"
            f"Reproduction steps:\n{steps_text}\n"
            f"Customer expected result: {expectation}\n"
            f"Customer observed result: {actual}\n"
            "After completing the execution, use the finish action to summarise the test. If anything is blocked, describe the issue explicitly."
        )

        return [
            {
                "name": "customer_issue_reproduction",
                "details": task_details,
                "scope": "functional",
                "steps": [],
            }
        ]

    def _interpret_run_result(self, issue: CustomerIssue, run_result: RunResult) -> TestOutcome:
        if not run_result.summary:
            return TestOutcome(status=TestStatus.UNCERTAIN, details="The test summary is empty; manual review may be required.")

        summary = run_result.summary[0]
        steps = summary.get("steps", []) if isinstance(summary, dict) else []

        finish_steps = [
            step
            for step in steps
            if isinstance(step, dict) and str(step.get("action", "")).lower() == "finish"
        ]
        error_steps = [
            step
            for step in steps
            if isinstance(step, dict)
            and "error" in str(step.get("result", "")).lower()
        ]

        known_issue_steps = [
            step
            for step in steps
            if isinstance(step, dict)
            and "known issue" in str(step.get("result", "")).lower()
        ]

        troubleshoot_steps = [
            step
            for step in steps
            if isinstance(step, dict)
            and "troubleshoot" in str(step.get("result", "")).lower()
        ]

        if finish_steps and not error_steps:
            result_detail = finish_steps[-1].get("result", "Test completed")
            return TestOutcome(
                status=TestStatus.PASSED,
                details=str(result_detail),
                report_path=run_result.summary_path,
            )

        if known_issue_steps:
            reference = known_issue_steps[-1].get("result")
            return TestOutcome(
                status=TestStatus.KNOWN_ISSUE,
                details=str(reference or "Confirmed as a known issue"),
                known_issue_reference=str(reference or ""),
                report_path=run_result.summary_path,
            )

        if troubleshoot_steps:
            reference = troubleshoot_steps[-1].get("result")
            return TestOutcome(
                status=TestStatus.TROUBLESHOOT_AVAILABLE,
                details=str(reference or "Provided troubleshooting steps"),
                troubleshoot_reference=str(reference or ""),
                report_path=run_result.summary_path,
            )

        if error_steps:
            detail = error_steps[-1].get("result", "Test failed")
            return TestOutcome(
                status=TestStatus.FAILED,
                details=str(detail),
                report_path=run_result.summary_path,
            )

        return TestOutcome(
            status=TestStatus.UNCERTAIN,
            details="The test did not complete cleanly or key information is missing.",
            report_path=run_result.summary_path,
        )

