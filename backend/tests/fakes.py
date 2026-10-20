"""Test doubles that implement the application ports."""
from typing import Iterator, List, Sequence

from app.application.conversation import AssistantMessage, LLMEvent, Message, TextDelta, ToolSpec, TurnComplete
from app.domain.ticket import Ticket


class ScriptedLLM:
    """LLMProvider that streams pre-scripted turns and records what it was sent."""

    def __init__(self, turns: Sequence[AssistantMessage]):
        self.turns = list(turns)
        self.calls: List[List[Message]] = []
        self.tools: List[Sequence[ToolSpec]] = []

    def stream(self, system: str, messages: Sequence[Message], tools: Sequence[ToolSpec]) -> Iterator[LLMEvent]:
        self.calls.append(list(messages))
        self.tools.append(tools)
        turn = self.turns.pop(0)
        if turn.text:
            yield TextDelta(turn.text)
        yield TurnComplete(turn)


class RecordingNotifier:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.sent: List[Ticket] = []

    def ticket_created(self, ticket: Ticket) -> bool:
        if self.fail:
            raise RuntimeError("notifier down")
        self.sent.append(ticket)
        return True
