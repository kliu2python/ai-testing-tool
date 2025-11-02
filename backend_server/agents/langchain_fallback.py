"""Lightweight fallbacks for LangChain components when the library is unavailable."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Sequence


class Runnable:
    """Minimal runnable abstraction mimicking LangChain's interface."""

    def invoke(self, input: Any, **kwargs: Any) -> Any:  # pragma: no cover - override expected
        raise NotImplementedError

    def __or__(self, other: "Runnable") -> "RunnableSequence":
        return RunnableSequence([self, other])


class RunnableSequence(Runnable):
    """Chain multiple runnables together."""

    def __init__(self, steps: Sequence[Runnable]):
        self.steps = list(steps)

    def __or__(self, other: Runnable) -> "RunnableSequence":
        return RunnableSequence(self.steps + [other])

    def invoke(self, input: Any, **kwargs: Any) -> Any:
        value = input
        for step in self.steps:
            value = step.invoke(value, **kwargs)
        return value


@dataclass
class ChatPromptTemplate(Runnable):
    """Very small chat prompt helper that joins message templates."""

    messages: List[Sequence[str]]

    @classmethod
    def from_messages(cls, messages: Iterable[Sequence[str]]) -> "ChatPromptTemplate":
        normalised = []
        for message in messages:
            role, content = message
            normalised.append((role, content))
        return cls(messages=normalised)

    def invoke(self, variables: Dict[str, Any], **kwargs: Any) -> str:
        rendered: List[str] = []
        for role, template in self.messages:
            rendered.append(template.format_map(variables))
        return "\n\n".join(rendered)


class StrOutputParser(Runnable):
    """Identity parser used to match LangChain's API."""

    def invoke(self, input: Any, **kwargs: Any) -> str:
        return str(input)

