"""Multi-agent workflow orchestrator connecting email, testing, and reporting."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from .data_models import (
    BugTicket,
    CustomerIssue,
    TestOutcome,
    TestStatus,
    WorkflowFunction,
    WorkflowResult,
    WorkflowStatus,
)
from .email_agent import EmailAgent
from .email_client import EmailSearchCriteria
from .mobile_agent import MobileTestAgent
from .mantis_agent import MantisTicketBuilder
from .qa_reporter import QAReporterAgent

logger = logging.getLogger(__name__)


@dataclass
class WorkflowConfig:
    """Configuration used for running the orchestrator."""

    issue_subject_keywords: Optional[List[str]] = None
    max_emails: int = 5
    enabled_functions: Optional[Set[WorkflowFunction]] = None


class MultiAgentOrchestrator:
    """Coordinate the full lifecycle from email intake to final report."""

    def __init__(
        self,
        email_agent: EmailAgent,
        mobile_agent: MobileTestAgent,
        reporter_agent: QAReporterAgent,
        config: Optional[WorkflowConfig] = None,
        mantis_builder: Optional[MantisTicketBuilder] = None,
        *,
        style_examples: Optional[Dict[str, List[str]]] = None,
    ) -> None:
        self.email_agent = email_agent
        self.mobile_agent = mobile_agent
        self.reporter_agent = reporter_agent
        self.config = config or WorkflowConfig()
        self.mantis_builder = mantis_builder or MantisTicketBuilder()
        self.style_examples = style_examples or {}

    async def run(self, customer_email: Optional[str]) -> Optional[WorkflowResult]:
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
            if self._is_enabled(WorkflowFunction.REQUEST_DETAILS):
                follow_up = self.email_agent.compose_follow_up(
                    issue,
                    missing,
                    style_examples=self._examples("follow_up_email"),
                )
                self.email_agent.send_email(
                    issue.customer_email, "Request for additional information", follow_up
                )
                report = self.reporter_agent.generate_pending_report(
                    issue,
                    missing,
                    style_examples=self._examples("qa_report"),
                )
                return self._build_result(
                    status=WorkflowStatus.AWAITING_CUSTOMER,
                    issue=issue,
                    outcome=None,
                    follow_up_email=follow_up,
                    resolution_email=None,
                    report=report,
                    actions=["requested_additional_information"],
                    mantis=None,
                )
            report = self.reporter_agent.generate_pending_report(
                issue,
                missing,
                style_examples=self._examples("qa_report"),
            )
            return self._build_result(
                status=WorkflowStatus.ESCALATED,
                issue=issue,
                outcome=None,
                follow_up_email=None,
                resolution_email=None,
                report=report,
                actions=["missing_information_without_follow_up"],
                mantis=self._maybe_build_ticket(issue, None),
            )

        if self._is_enabled(WorkflowFunction.AUTO_TEST):
            outcome = await self.mobile_agent.execute(issue)
            actions.append(outcome.status.value)
        else:
            outcome = TestOutcome(
                status=TestStatus.NOT_RUN,
                details="Automation disabled by subscription settings.",
            )
            actions.append("automation_skipped")

        if outcome.status == TestStatus.MISSING_INFORMATION:
            if self._is_enabled(WorkflowFunction.REQUEST_DETAILS):
                follow_up = self.email_agent.compose_follow_up(
                    issue,
                    outcome.missing_information or ["additional details"],
                    style_examples=self._examples("follow_up_email"),
                )
                self.email_agent.send_email(
                    issue.customer_email, "Request for additional information", follow_up
                )
                report = self.reporter_agent.generate_pending_report(
                    issue,
                    outcome.missing_information or ["additional details"],
                    style_examples=self._examples("qa_report"),
                )
                return self._build_result(
                    status=WorkflowStatus.AWAITING_CUSTOMER,
                    issue=issue,
                    outcome=outcome,
                    follow_up_email=follow_up,
                    resolution_email=None,
                    report=report,
                    actions=actions,
                    mantis=None,
                )
            report = self.reporter_agent.generate_pending_report(
                issue,
                outcome.missing_information or ["additional details"],
                style_examples=self._examples("qa_report"),
            )
            return self._build_result(
                status=WorkflowStatus.ESCALATED,
                issue=issue,
                outcome=outcome,
                follow_up_email=None,
                resolution_email=None,
                report=report,
                actions=actions + ["missing_information_without_follow_up"],
                mantis=self._maybe_build_ticket(issue, outcome),
            )

        if outcome.status in {
            TestStatus.PASSED,
            TestStatus.KNOWN_ISSUE,
            TestStatus.TROUBLESHOOT_AVAILABLE,
            TestStatus.NOT_RUN,
        }:
            report = self.reporter_agent.generate_report(
                issue,
                outcome,
                style_examples=self._examples("qa_report"),
            )
            resolution: Optional[str] = None
            if self._is_enabled(WorkflowFunction.PUBLIC_RESPONSE) and outcome.status != TestStatus.NOT_RUN:
                summary = self._render_outcome_summary(outcome)
                resolution = self.email_agent.compose_resolution(
                    issue,
                    summary,
                    style_examples=self._examples("resolution_email"),
                )
                self.email_agent.send_email(issue.customer_email, "Test results update", resolution)
            return self._build_result(
                status=WorkflowStatus.RESOLVED,
                issue=issue,
                outcome=outcome,
                follow_up_email=None,
                resolution_email=resolution,
                report=report,
                actions=actions,
                mantis=self._maybe_build_ticket(issue, outcome),
            )

        # Failed or uncertain -> escalate
        report = self.reporter_agent.generate_report(
            issue,
            outcome,
            style_examples=self._examples("qa_report"),
        )
        return self._build_result(
            status=WorkflowStatus.ESCALATED,
            issue=issue,
            outcome=outcome,
            follow_up_email=None,
            resolution_email=None,
            report=report,
            actions=actions + ["escalated"],
            mantis=self._maybe_build_ticket(issue, outcome),
        )

    def _render_outcome_summary(self, outcome: TestOutcome) -> str:
        if outcome.status == TestStatus.PASSED:
            return f"Successfully reproduced and validated the issue. Details: {outcome.details}"
        if outcome.status == TestStatus.KNOWN_ISSUE:
            return f"Confirmed known issue: {outcome.known_issue_reference or outcome.details}"
        if outcome.status == TestStatus.TROUBLESHOOT_AVAILABLE:
            return f"Provided troubleshooting steps: {outcome.troubleshoot_reference or outcome.details}"
        return outcome.details

    def _is_enabled(self, feature: WorkflowFunction) -> bool:
        if not self.config.enabled_functions:
            return True
        return feature in self.config.enabled_functions

    def _maybe_build_ticket(self, issue: CustomerIssue, outcome: Optional[TestOutcome]) -> Optional[BugTicket]:
        if not self._is_enabled(WorkflowFunction.CREATE_MANTIS_TICKET):
            return None
        return self.mantis_builder.build(
            issue,
            outcome,
            style_examples=self._examples("mantis_ticket"),
        )

    def _examples(self, key: str) -> List[str]:
        return list(self.style_examples.get(key) or [])

    def _build_result(
        self,
        *,
        status: WorkflowStatus,
        issue: CustomerIssue,
        outcome: Optional[TestOutcome],
        follow_up_email: Optional[str],
        resolution_email: Optional[str],
        report: str,
        actions: List[str],
        mantis: Optional[BugTicket],
    ) -> WorkflowResult:
        return WorkflowResult(
            status=status,
            issue=issue,
            outcome=outcome,
            follow_up_email=follow_up_email,
            resolution_email=resolution_email,
            report=report,
            actions=actions,
            mantis_ticket=mantis,
        )

