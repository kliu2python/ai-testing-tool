"""Multi-agent workflow orchestrator connecting email, testing, and reporting."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

from .data_models import (
    CustomerIssue,
    TestOutcome,
    TestStatus,
    WorkflowResult,
    WorkflowStatus,
)
from .email_agent import EmailAgent
from .email_client import EmailSearchCriteria
from .mobile_agent import MobileTestAgent
from .qa_reporter import QAReporterAgent

logger = logging.getLogger(__name__)


@dataclass
class WorkflowConfig:
    """Configuration used for running the orchestrator."""

    issue_subject_keywords: Optional[List[str]] = None
    max_emails: int = 5


class MultiAgentOrchestrator:
    """Coordinate the full lifecycle from email intake to final report."""

    def __init__(
        self,
        email_agent: EmailAgent,
        mobile_agent: MobileTestAgent,
        reporter_agent: QAReporterAgent,
        config: Optional[WorkflowConfig] = None,
    ) -> None:
        self.email_agent = email_agent
        self.mobile_agent = mobile_agent
        self.reporter_agent = reporter_agent
        self.config = config or WorkflowConfig()

    async def run(self, customer_email: str) -> Optional[WorkflowResult]:
        criteria = EmailSearchCriteria(
            sender=customer_email,
            subject_keywords=self.config.issue_subject_keywords,
            limit=self.config.max_emails,
        )
        issue = self.email_agent.fetch_latest_issue(criteria)
        if not issue:
            logger.info("No matching email found for %s", customer_email)
            return None

        actions: List[str] = []

        missing = issue.missing_required_fields()
        if missing:
            logger.info("Issue missing required fields: %s", missing)
            follow_up = self.email_agent.compose_follow_up(issue, missing)
            self.email_agent.send_email(issue.customer_email, "Request for additional information", follow_up)
            report = self.reporter_agent.generate_pending_report(issue, missing)
            return WorkflowResult(
                status=WorkflowStatus.AWAITING_CUSTOMER,
                issue=issue,
                outcome=None,
                follow_up_email=follow_up,
                resolution_email=None,
                report=report,
                actions=["requested_additional_information"],
            )

        outcome = await self.mobile_agent.execute(issue)
        actions.append(outcome.status.value)

        if outcome.status == TestStatus.MISSING_INFORMATION:
            follow_up = self.email_agent.compose_follow_up(issue, outcome.missing_information or ["additional details"])
            self.email_agent.send_email(issue.customer_email, "Request for additional information", follow_up)
            report = self.reporter_agent.generate_pending_report(
                issue, outcome.missing_information or ["additional details"]
            )
            return WorkflowResult(
                status=WorkflowStatus.AWAITING_CUSTOMER,
                issue=issue,
                outcome=outcome,
                follow_up_email=follow_up,
                resolution_email=None,
                report=report,
                actions=actions,
            )

        if outcome.status in {
            TestStatus.PASSED,
            TestStatus.KNOWN_ISSUE,
            TestStatus.TROUBLESHOOT_AVAILABLE,
        }:
            summary = self._render_outcome_summary(outcome)
            resolution = self.email_agent.compose_resolution(issue, summary)
            self.email_agent.send_email(issue.customer_email, "Test results update", resolution)
            report = self.reporter_agent.generate_report(issue, outcome)
            return WorkflowResult(
                status=WorkflowStatus.RESOLVED,
                issue=issue,
                outcome=outcome,
                follow_up_email=None,
                resolution_email=resolution,
                report=report,
                actions=actions,
            )

        # Failed or uncertain -> escalate
        report = self.reporter_agent.generate_report(issue, outcome)
        return WorkflowResult(
            status=WorkflowStatus.ESCALATED,
            issue=issue,
            outcome=outcome,
            follow_up_email=None,
            resolution_email=None,
            report=report,
            actions=actions + ["escalated"],
        )

    def _render_outcome_summary(self, outcome: TestOutcome) -> str:
        if outcome.status == TestStatus.PASSED:
            return f"Successfully reproduced and validated the issue. Details: {outcome.details}"
        if outcome.status == TestStatus.KNOWN_ISSUE:
            return f"Confirmed known issue: {outcome.known_issue_reference or outcome.details}"
        if outcome.status == TestStatus.TROUBLESHOOT_AVAILABLE:
            return f"Provided troubleshooting steps: {outcome.troubleshoot_reference or outcome.details}"
        return outcome.details

