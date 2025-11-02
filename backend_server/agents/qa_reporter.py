"""QA reporter agent responsible for generating summaries for stakeholders."""

from __future__ import annotations

try:  # pragma: no cover - import guard for environments without LangChain
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.runnables import Runnable
except ImportError:  # pragma: no cover - fallback
    from .langchain_fallback import ChatPromptTemplate, Runnable, StrOutputParser

from typing import List, Optional

from .data_models import CustomerIssue, TestOutcome, TestStatus


class QAReporterAgent:
    """Generate reports for customer support or engineering teams."""

    def __init__(self, llm: Runnable):
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a professional QA report writer who produces structured, easy-to-read reports in English.",
                ),
                (
                    "human",
                    "Issue details:\n{issue_description}\n"
                    "Test result: {test_result}\n"
                    "Style guidance:\n{style_examples}\n"
                    "Please provide a report containing a summary, execution environment, reproduction steps, conclusion, and next recommendations.",
                ),
            ]
        )
        pending_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a QA report writer summarising current progress and highlighting missing information.",
                ),
                (
                    "human",
                    "Issue details:\n{issue_description}\n"
                    "Missing information:\n{missing_info}\n"
                    "Style guidance:\n{style_examples}\n"
                    "Compose a report that emphasises what the customer still needs to provide and the planned next steps.",
                ),
            ]
        )
        self._report_chain = prompt | llm | StrOutputParser()
        self._pending_chain = pending_prompt | llm | StrOutputParser()

    def generate_report(
        self,
        issue: CustomerIssue,
        outcome: TestOutcome,
        *,
        style_examples: Optional[List[str]] = None,
    ) -> str:
        description = issue.describe()
        status_text = self._render_status(outcome)
        return self._report_chain.invoke(
            {
                "issue_description": description,
                "test_result": status_text,
                "style_examples": self._render_style_examples(style_examples),
            }
        )

    def generate_pending_report(
        self,
        issue: CustomerIssue,
        missing_info: list[str],
        *,
        style_examples: Optional[List[str]] = None,
    ) -> str:
        description = issue.describe()
        missing = "\n".join(f"- {item}" for item in missing_info)
        return self._pending_chain.invoke(
            {
                "issue_description": description,
                "missing_info": missing,
                "style_examples": self._render_style_examples(style_examples),
            }
        )

    def _render_status(self, outcome: TestOutcome) -> str:
        mapping = {
            TestStatus.PASSED: "Testing succeeded and the steps were reproduced successfully.",
            TestStatus.FAILED: f"Testing failed: {outcome.details}",
            TestStatus.KNOWN_ISSUE: f"Confirmed known issue: {outcome.known_issue_reference or outcome.details}",
            TestStatus.TROUBLESHOOT_AVAILABLE: (
                f"Provided troubleshooting guidance: {outcome.troubleshoot_reference or outcome.details}"
            ),
            TestStatus.MISSING_INFORMATION: f"Missing information: {', '.join(outcome.missing_information)}",
            TestStatus.UNCERTAIN: outcome.details,
            TestStatus.NOT_RUN: "Automation was skipped for this request.",
        }
        return mapping[outcome.status]

    @staticmethod
    def _render_style_examples(examples: Optional[List[str]]) -> str:
        if not examples:
            return "No specific style preferences provided."
        formatted = []
        for idx, example in enumerate(examples[:5], start=1):
            formatted.append(f"Example {idx}:\n{example.strip()}")
        return "\n\n".join(formatted)

