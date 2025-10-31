"""Email client abstractions used by the email agent."""

from __future__ import annotations

import imaplib
import smtplib
from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage as StdEmailMessage
from email.parser import BytesParser
from email.policy import default as default_policy
from email.utils import parsedate_to_datetime
from typing import Iterable, Iterator, List, Optional

from .data_models import EmailMessage


@dataclass
class EmailSearchCriteria:
    """Filter used when retrieving relevant emails."""

    sender: Optional[str] = None
    subject_keywords: Optional[List[str]] = None
    limit: int = 5


class EmailClient(ABC):
    """Interface used by the email agent to interact with the mailbox."""

    @abstractmethod
    def search(self, criteria: EmailSearchCriteria) -> List[EmailMessage]:
        """Return messages that match ``criteria`` ordered by recency."""

    @abstractmethod
    def send(self, to: str, subject: str, body: str) -> None:
        """Send an email."""


class InMemoryEmailClient(EmailClient):
    """Lightweight client used for tests or local prototyping."""

    def __init__(self, messages: Optional[Iterable[EmailMessage]] = None):
        self._messages: List[EmailMessage] = list(messages or [])
        self.sent_messages: List[StdEmailMessage] = []

    def add(self, message: EmailMessage) -> None:
        self._messages.append(message)

    def search(self, criteria: EmailSearchCriteria) -> List[EmailMessage]:
        results = list(self._messages)
        if criteria.sender:
            results = [m for m in results if m.sender.lower() == criteria.sender.lower()]
        if criteria.subject_keywords:
            lowered = [kw.lower() for kw in criteria.subject_keywords]
            results = [
                m
                for m in results
                if any(keyword in m.subject.lower() for keyword in lowered)
            ]
        results.sort(key=lambda msg: msg.received_at, reverse=True)
        return results[: criteria.limit]

    def send(self, to: str, subject: str, body: str) -> None:
        message = StdEmailMessage()
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        self.sent_messages.append(message)


class ImapEmailClient(EmailClient):
    """IMAP + SMTP based implementation for production usage."""

    def __init__(
        self,
        imap_host: str,
        username: str,
        password: str,
        mailbox: str = "INBOX",
        use_ssl: bool = True,
        smtp_host: Optional[str] = None,
        smtp_port: Optional[int] = None,
    ) -> None:
        self.imap_host = imap_host
        self.username = username
        self.password = password
        self.mailbox = mailbox
        self.use_ssl = use_ssl
        self.smtp_host = smtp_host or imap_host
        self.smtp_port = smtp_port or (465 if use_ssl else 587)

    @contextmanager
    def _imap_connection(self) -> Iterator[imaplib.IMAP4]:
        client: imaplib.IMAP4
        if self.use_ssl:
            client = imaplib.IMAP4_SSL(self.imap_host)
        else:
            client = imaplib.IMAP4(self.imap_host)
        try:
            client.login(self.username, self.password)
            client.select(self.mailbox)
            yield client
        finally:
            try:
                client.logout()
            except Exception:
                pass

    def search(self, criteria: EmailSearchCriteria) -> List[EmailMessage]:
        query = ["ALL"]
        if criteria.sender:
            query.extend(["FROM", criteria.sender])
        if criteria.subject_keywords:
            for keyword in criteria.subject_keywords:
                query.extend(["SUBJECT", keyword])

        with self._imap_connection() as conn:
            status, data = conn.search(None, *query)
            if status != "OK":
                return []

            message_ids = data[0].split()
            message_ids.reverse()
            results: List[EmailMessage] = []
            for msg_id in message_ids[: criteria.limit]:
                status, payload = conn.fetch(msg_id, "(RFC822)")
                if status != "OK" or not payload:
                    continue
                raw = payload[0][1]
                email_obj = BytesParser(policy=default_policy).parsebytes(raw)
                body = email_obj.get_body(preferencelist=("plain", "html"))
                content = body.get_content() if body else ""
                received = email_obj.get("Date")
                try:
                    received_at = parsedate_to_datetime(received) if received else datetime.utcnow()
                except Exception:
                    received_at = datetime.utcnow()

                results.append(
                    EmailMessage(
                        subject=email_obj.get("Subject", ""),
                        sender=email_obj.get("From", ""),
                        body=content,
                        received_at=received_at,
                        message_id=email_obj.get("Message-ID"),
                    )
                )

        return results

    def send(self, to: str, subject: str, body: str) -> None:
        message = StdEmailMessage()
        message["From"] = self.username
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)

        if self.use_ssl:
            smtp = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port)
        else:
            smtp = smtplib.SMTP(self.smtp_host, self.smtp_port)
        try:
            if not self.use_ssl:
                smtp.starttls()
            smtp.login(self.username, self.password)
            smtp.send_message(message)
        finally:
            smtp.quit()

