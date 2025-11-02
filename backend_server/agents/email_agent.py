"""LangChain powered email agent for extracting and responding to issues."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import List, Optional

try:  # pragma: no cover - import guard for environments without LangChain
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.runnables import Runnable
except ImportError:  # pragma: no cover - fallback
    from .langchain_fallback import ChatPromptTemplate, Runnable, StrOutputParser

from .data_models import CustomerIssue
from .email_client import EmailClient, EmailSearchCriteria

logger = logging.getLogger(__name__)


@dataclass
class IssueExtraction:
    """Structured payload parsed from the LLM output."""

    platform: Optional[str]
    os_version: Optional[str]
    app_version: Optional[str]
    steps: List[str]
    expected_result: Optional[str]
    actual_result: Optional[str]

    @classmethod
    def from_raw(cls, raw: str) -> "IssueExtraction":
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning("Issue extraction JSON malformed: %s", exc)
            data = {}

        if not isinstance(data, dict):
            data = {}

        def _normalise_list(value: object) -> List[str]:
            if isinstance(value, list):
                return [str(item).strip() for item in value if str(item).strip()]
            if isinstance(value, str):
                return [line.strip() for line in value.splitlines() if line.strip()]
            return []

        return cls(
            platform=str(data.get("platform") or "") or None,
            os_version=str(data.get("os_version") or "") or None,
            app_version=str(data.get("app_version") or "") or None,
            steps=_normalise_list(data.get("steps")),
            expected_result=str(data.get("expected_result") or "") or None,
            actual_result=str(data.get("actual_result") or "") or None,
        )


class EmailAgent:
    """Agent responsible for understanding emails and composing responses."""

    def __init__(self, client: EmailClient, llm: Runnable):
        self.client = client
        self.llm = llm
        self._issue_chain = self._build_issue_chain(llm)
        self._followup_chain = self._build_followup_chain(llm)
        self._resolution_chain = self._build_resolution_chain(llm)

    def _build_issue_chain(self, llm: Runnable) -> Runnable:
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a professional QA engineer. Extract the key information from the customer's email and return it as JSON."
                    "The JSON keys must include platform, os_version, app_version, steps, expected_result, actual_result."
                    "steps must be an array where each entry is a concise step description.",
                ),
                (
                    "human",
                    "Subject: {subject}\n"
                    "Sender: {sender}\n"
                    "Body:\n{body}\n"
                    "Return JSON only with no extra commentary.",
                ),
            ]
        )
        return prompt | llm | StrOutputParser()

    def _build_followup_chain(self, llm: Runnable) -> Runnable:
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a professional and empathetic support agent asking the customer for more information politely."
                    "The email must include appreciation, a list of missing details, and guidance on how to provide them.",
                ),
                (
                    "human",
                    "Customer email: {customer_email}\n"
                    "Issue summary:\n{issue_summary}\n"
                    "Missing details: {missing_items}\n"
                    "Style guidance:\n{style_examples}\n"
                    "Please write the email in English.",
                ),
            ]
        )
        return prompt | llm | StrOutputParser()

    def _build_resolution_chain(self, llm: Runnable) -> Runnable:
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a senior QA engineer providing customers with the test results."
                    "The email should summarise the test conclusion, key reproduction steps, and recommended next actions.",
                ),
                (
                    "human",
                    "Customer email: {customer_email}\n"
                    "Issue summary:\n{issue_summary}\n"
                    "Test conclusion: {test_summary}\n"
                    "Style guidance:\n{style_examples}\n"
                    "Please write the email in English.",
                ),
            ]
        )
        return prompt | llm | StrOutputParser()

    def fetch_latest_issue(self, criteria: EmailSearchCriteria) -> Optional[CustomerIssue]:
        messages = self.client.search(criteria)
        if not messages:
            return None

        # Use the most recent message
        message = messages[0]
        extraction_raw = self._issue_chain.invoke(
            {"subject": message.subject, "sender": message.sender, "body": message.body}
        )
        extraction = IssueExtraction.from_raw(extraction_raw)

        return CustomerIssue(
            customer_email=message.sender,
            subject=message.subject,
            body=message.body,
            platform=extraction.platform,
            os_version=extraction.os_version,
            app_version=extraction.app_version,
            steps=extraction.steps,
            expected_result=extraction.expected_result,
            actual_result=extraction.actual_result,
            metadata={"message_id": message.message_id or ""},
        )

    def compose_follow_up(
        self,
        issue: CustomerIssue,
        missing_items: List[str],
        *,
        style_examples: Optional[List[str]] = None,
    ) -> str:
        missing_text = "\n".join(f"- {item}" for item in missing_items)
        return self._followup_chain.invoke(
            {
                "customer_email": issue.customer_email,
                "issue_summary": issue.describe(),
                "missing_items": missing_text,
                "style_examples": self._render_style_examples(style_examples),
            }
        )

    def compose_resolution(
        self,
        issue: CustomerIssue,
        summary: str,
        *,
        style_examples: Optional[List[str]] = None,
    ) -> str:
        return self._resolution_chain.invoke(
            {
                "customer_email": issue.customer_email,
                "issue_summary": issue.describe(),
                "test_summary": summary,
                "style_examples": self._render_style_examples(style_examples),
            }
        )

    def send_email(self, to: str, subject: str, body: str) -> None:
        logger.info("Sending email to %s with subject '%s'", to, subject)
        self.client.send(to, subject, body)

    @staticmethod
    def _render_style_examples(examples: Optional[List[str]]) -> str:
        if not examples:
            return "No specific style preferences provided."
        formatted = []
        for idx, example in enumerate(examples[:5], start=1):
            formatted.append(f"Example {idx}:\n{example.strip()}")
        return "\n\n".join(formatted)

