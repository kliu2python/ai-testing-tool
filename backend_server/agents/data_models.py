"""Data models shared by the multi-agent workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional


class TestStatus(str, Enum):
    """Possible outcomes of a mobile automation run."""

    PASSED = "passed"
    FAILED = "failed"
    MISSING_INFORMATION = "missing_information"
    KNOWN_ISSUE = "known_issue"
    TROUBLESHOOT_AVAILABLE = "troubleshoot_available"
    UNCERTAIN = "uncertain"


class WorkflowStatus(str, Enum):
    """High level state of the multi-agent workflow."""

    RESOLVED = "resolved"
    AWAITING_CUSTOMER = "awaiting_customer"
    ESCALATED = "escalated"


@dataclass
class EmailMessage:
    """Simplified representation of an email message."""

    subject: str
    sender: str
    body: str
    received_at: datetime
    message_id: Optional[str] = None
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class CustomerIssue:
    """Structured description of a customer's problem."""

    customer_email: str
    subject: str
    body: str
    platform: Optional[str]
    os_version: Optional[str]
    app_version: Optional[str]
    steps: List[str]
    expected_result: Optional[str]
    actual_result: Optional[str]
    metadata: Dict[str, str] = field(default_factory=dict)

    def missing_required_fields(self) -> List[str]:
        """Return a list of critical fields that are absent."""

        missing: List[str] = []
        if not self.platform:
            missing.append("platform")
        if not self.steps:
            missing.append("steps")
        if not self.app_version:
            missing.append("app_version")
        if (self.platform or "").lower() in {"android", "ios"} and not self.os_version:
            missing.append("os_version")
        return missing

    def describe(self) -> str:
        """Return a human readable description used by downstream agents."""

        bullet_steps = "\n".join(f"{idx + 1}. {step}" for idx, step in enumerate(self.steps))
        expected = self.expected_result or "(not provided)"
        actual = self.actual_result or "(not provided)"
        platform = self.platform or "(not provided)"
        os_version = self.os_version or "(not provided)"
        app_version = self.app_version or "(not provided)"
        return (
            f"Customer email: {self.customer_email}\n"
            f"Issue subject: {self.subject}\n"
            f"Platform: {platform}\n"
            f"OS version: {os_version}\n"
            f"App version: {app_version}\n"
            f"Expected result: {expected}\n"
            f"Actual result: {actual}\n"
            "Reproduction steps:\n" + (bullet_steps or "(not provided)")
        )


@dataclass
class TestOutcome:
    """Result returned by the mobile automation agent."""

    status: TestStatus
    details: str
    missing_information: List[str] = field(default_factory=list)
    known_issue_reference: Optional[str] = None
    troubleshoot_reference: Optional[str] = None
    report_path: Optional[str] = None


@dataclass
class WorkflowResult:
    """Aggregated outcome for the orchestrated workflow."""

    status: WorkflowStatus
    issue: CustomerIssue
    outcome: Optional[TestOutcome]
    follow_up_email: Optional[str]
    resolution_email: Optional[str]
    report: str
    actions: List[str] = field(default_factory=list)

