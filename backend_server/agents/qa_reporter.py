"""QA reporter agent responsible for generating summaries for stakeholders."""

from __future__ import annotations

try:  # pragma: no cover - import guard for environments without LangChain
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.runnables import Runnable
except ImportError:  # pragma: no cover - fallback
    from .langchain_fallback import ChatPromptTemplate, Runnable, StrOutputParser

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
                    "Compose a report that emphasises what the customer still needs to provide and the planned next steps.",
                ),
            ]
        )
        self._report_chain = prompt | llm | StrOutputParser()
        self._pending_chain = pending_prompt | llm | StrOutputParser()

    def generate_report(self, issue: CustomerIssue, outcome: TestOutcome) -> str:
        description = issue.describe()
        status_text = self._render_status(outcome)
        return self._report_chain.invoke(
            {"issue_description": description, "test_result": status_text}
        )

    def generate_pending_report(self, issue: CustomerIssue, missing_info: list[str]) -> str:
        description = issue.describe()
        missing = "\n".join(f"- {item}" for item in missing_info)
        return self._pending_chain.invoke(
            {"issue_description": description, "missing_info": missing}
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
        }
        return mapping[outcome.status]

