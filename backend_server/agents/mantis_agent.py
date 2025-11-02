"""Helper for generating Mantis-compatible ticket drafts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .data_models import BugTicket, CustomerIssue, TestOutcome, TestStatus


@dataclass
class MantisTicketBuilder:
    """Create lightweight ticket payloads from workflow results."""

    default_severity: str = "major"

    def build(self, issue: CustomerIssue, outcome: Optional[TestOutcome]) -> BugTicket:
        """Generate a ``BugTicket`` based on ``issue`` and ``outcome``."""

        severity = self._resolve_severity(outcome)
        title = issue.subject or "Mobile issue report"
        description = self._compose_description(issue, outcome)
        tags: List[str] = []
        if issue.platform:
            tags.append(issue.platform.lower())
        if outcome and outcome.status == TestStatus.KNOWN_ISSUE:
            tags.append("known-issue")

        return BugTicket(
            title=title,
            description=description,
            steps_to_reproduce=list(issue.steps),
            expected_result=issue.expected_result,
            actual_result=issue.actual_result,
            severity=severity,
            tags=tags,
        )

    def _resolve_severity(self, outcome: Optional[TestOutcome]) -> str:
        if not outcome:
            return self.default_severity
        if outcome.status == TestStatus.FAILED:
            return "critical"
        if outcome.status == TestStatus.KNOWN_ISSUE:
            return "major"
        if outcome.status in {TestStatus.PASSED, TestStatus.NOT_RUN}:
            return "minor"
        return self.default_severity

    def _compose_description(self, issue: CustomerIssue, outcome: Optional[TestOutcome]) -> str:
        details = [issue.describe()]
        if outcome:
            details.append(f"Test outcome: {outcome.status.value} - {outcome.details}")
            if outcome.report_path:
                details.append(f"Report path: {outcome.report_path}")
        else:
            details.append("Automation was not executed for this ticket.")
        return "\n\n".join(details)

