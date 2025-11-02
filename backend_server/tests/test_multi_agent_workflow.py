"""Unit tests for the LangChain multi-agent workflow."""

from __future__ import annotations

import asyncio
import datetime as dt
from typing import List

from backend_server.agents import (
    BugTicket,
    CustomerIssue,
    EmailAgent,
    EmailMessage,
    InMemoryEmailClient,
    MobileProxyClient,
    MobileTestAgent,
    QAReporterAgent,
    TestOutcome,
    TestStatus,
    WorkflowConfig,
    WorkflowFunction,
    WorkflowStatus,
)
from backend_server.agents.mobile_agent import DeviceDescriptor
from backend_server.agents.orchestrator import MultiAgentOrchestrator
from backend_server.runner import RunResult


class SequencedLLM:
    """Minimal LLM stub that returns predefined outputs sequentially."""

    def __init__(self, responses: List[str]):
        self._responses = list(responses)
        self.invocations: List[dict] = []

    def invoke(self, prompt, **kwargs):  # type: ignore[override]
        self.invocations.append({"prompt": prompt, **kwargs})
        if not self._responses:
            raise RuntimeError("No more responses configured for SequencedLLM")
        return self._responses.pop(0)


class StubMobileAgent:
    """Lightweight replacement for the mobile agent in orchestrator tests."""

    def __init__(self, outcome: TestOutcome) -> None:
        self.outcome = outcome
        self.calls: List[CustomerIssue] = []

    async def execute(self, issue: CustomerIssue) -> TestOutcome:
        self.calls.append(issue)
        return self.outcome


class StubAutomationRunner:
    """Fake automation runner returning a predefined summary."""

    def __init__(self, summary: List[dict]) -> None:
        self.summary = summary
        self.calls = []

    async def run(self, tasks, device, llm_mode=None) -> RunResult:
        self.calls.append((tasks, device, llm_mode))
        return RunResult(summary=self.summary, summary_path="/tmp/report.json")


def _email_message(body: str) -> EmailMessage:
    return EmailMessage(
        subject="Customer issue",
        sender="customer@example.com",
        body=body,
        received_at=dt.datetime.utcnow(),
    )


def test_orchestrator_requests_missing_information() -> None:
    json_payload = (
        '{"platform": "android", "app_version": "5.2", '
        '"steps": ["Open the app"], "expected_result": "Success", "actual_result": "Crash"}'
    )
    email_llm = SequencedLLM([json_payload, "Please provide the OS version."])
    reporter_llm = SequencedLLM(["Awaiting additional information report"])

    email_client = InMemoryEmailClient([_email_message("Sample email")])
    email_agent = EmailAgent(email_client, email_llm)

    mobile_agent = StubMobileAgent(
        TestOutcome(status=TestStatus.PASSED, details="Should not be invoked")
    )
    reporter = QAReporterAgent(reporter_llm)

    orchestrator = MultiAgentOrchestrator(
        email_agent,
        mobile_agent,
        reporter,
        WorkflowConfig(issue_subject_keywords=["issue"], max_emails=1),
    )

    result = asyncio.run(orchestrator.run("customer@example.com"))

    assert result is not None
    assert result.status == WorkflowStatus.AWAITING_CUSTOMER
    assert "OS version" in result.follow_up_email
    assert "Awaiting additional information report" in result.report
    assert len(email_client.sent_messages) == 1
    assert mobile_agent.calls == []


def test_orchestrator_handles_successful_run() -> None:
    json_payload = (
        '{"platform": "ios", "os_version": "17.4", "app_version": "5.2", '
        '"steps": ["Open the app", "Log in"], "expected_result": "Success", "actual_result": "Crash"}'
    )
    email_llm = SequencedLLM([json_payload, "Thank you for the details—we have reproduced the issue."])
    reporter_llm = SequencedLLM(["Final report"])

    email_client = InMemoryEmailClient([_email_message("Another email")])
    email_agent = EmailAgent(email_client, email_llm)

    outcome = TestOutcome(status=TestStatus.PASSED, details="Successfully reproduced", report_path="/tmp/report.json")
    mobile_agent = StubMobileAgent(outcome)
    reporter = QAReporterAgent(reporter_llm)

    orchestrator = MultiAgentOrchestrator(
        email_agent,
        mobile_agent,
        reporter,
        WorkflowConfig(issue_subject_keywords=["issue"], max_emails=1),
    )

    result = asyncio.run(orchestrator.run("customer@example.com"))

    assert result is not None
    assert result.status == WorkflowStatus.RESOLVED
    assert result.resolution_email == "Thank you for the details—we have reproduced the issue."
    assert result.outcome == outcome
    assert result.report == "Final report"
    assert len(email_client.sent_messages) == 1
    assert mobile_agent.calls
    assert isinstance(result.mantis_ticket, BugTicket)
    assert result.mantis_ticket.title == "Customer issue"


def test_orchestrator_skips_automation_when_disabled() -> None:
    json_payload = (
        '{"platform": "ios", "os_version": "17.4", "app_version": "5.2", '
        '"steps": ["Open the app", "Log in"], "expected_result": "Success", "actual_result": "Crash"}'
    )
    email_llm = SequencedLLM([json_payload, "Automation is disabled but we captured the request."])
    reporter_llm = SequencedLLM(["Automation skipped report"])

    email_client = InMemoryEmailClient([_email_message("Another email")])
    email_agent = EmailAgent(email_client, email_llm)

    outcome = TestOutcome(status=TestStatus.PASSED, details="Would have reproduced")
    mobile_agent = StubMobileAgent(outcome)
    reporter = QAReporterAgent(reporter_llm)

    enabled = {
        WorkflowFunction.PUBLIC_RESPONSE,
        WorkflowFunction.CREATE_MANTIS_TICKET,
    }
    orchestrator = MultiAgentOrchestrator(
        email_agent,
        mobile_agent,
        reporter,
        WorkflowConfig(issue_subject_keywords=["issue"], max_emails=1, enabled_functions=enabled),
    )

    result = asyncio.run(orchestrator.run("customer@example.com"))

    assert result is not None
    assert result.status == WorkflowStatus.RESOLVED
    assert result.outcome is not None
    assert result.outcome.status == TestStatus.NOT_RUN
    assert "automation_skipped" in result.actions
    assert result.resolution_email is None
    assert mobile_agent.calls == []
    assert isinstance(result.mantis_ticket, BugTicket)


def test_orchestrator_does_not_request_details_when_disabled() -> None:
    json_payload = (
        '{"platform": "android", "app_version": "5.2", '
        '"steps": ["Open"], "expected_result": "Success", "actual_result": "Crash"}'
    )
    email_llm = SequencedLLM([json_payload, "Follow up disabled."])
    reporter_llm = SequencedLLM(["Missing info escalation"])

    email_client = InMemoryEmailClient([_email_message("Sample email")])
    email_agent = EmailAgent(email_client, email_llm)

    mobile_outcome = TestOutcome(
        status=TestStatus.MISSING_INFORMATION,
        details="Need OS version",
        missing_information=["os_version"],
    )
    mobile_agent = StubMobileAgent(mobile_outcome)
    reporter = QAReporterAgent(reporter_llm)

    enabled = {
        WorkflowFunction.AUTO_TEST,
        WorkflowFunction.CREATE_MANTIS_TICKET,
    }
    orchestrator = MultiAgentOrchestrator(
        email_agent,
        mobile_agent,
        reporter,
        WorkflowConfig(issue_subject_keywords=["issue"], max_emails=1, enabled_functions=enabled),
    )

    result = asyncio.run(orchestrator.run("customer@example.com"))

    assert result is not None
    assert result.status == WorkflowStatus.ESCALATED
    assert result.follow_up_email is None
    assert result.actions[-1] == "missing_information_without_follow_up"
    assert isinstance(result.mantis_ticket, BugTicket)


def test_mobile_agent_interprets_finish_status() -> None:
    device = DeviceDescriptor(name="qa-android", platform="android", server="http://localhost:4723", os_version="14")
    proxy = MobileProxyClient([device])
    summary = [{"steps": [{"action": "finish", "result": "Validated"}]}]
    runner = StubAutomationRunner(summary)
    agent = MobileTestAgent(proxy, runner)

    issue = CustomerIssue(
        customer_email="customer@example.com",
        subject="Test",
        body="",
        platform="android",
        os_version="14",
        app_version="5.0",
        steps=["Open the app"],
        expected_result="Success",
        actual_result="Crash",
    )

    outcome = asyncio.run(agent.execute(issue))

    assert outcome.status == TestStatus.PASSED
    assert "Validated" in outcome.details
    assert runner.calls  # ensure runner was invoked

