"""Ports: the application's boundary with the outside world, on both sides.

- Driving port (`ChatUseCase`): how the outside calls the application. The API
  and the tests depend on it, never on the class that implements it.
- Driven ports (the rest): what the application needs from the outside.
  Adapters in `app.infrastructure` implement them; the application never
  imports an adapter directly.
"""
from dataclasses import dataclass
from typing import Iterator, List, Protocol, Sequence, Union, runtime_checkable

from app.application.conversation import LLMEvent, Message, TextDelta, ToolSpec
from app.domain.rate_limit import RateLimitDecision
from app.domain.ticket import Ticket


# --- Driving port ---------------------------------------------------------


@dataclass(frozen=True)
class ToolStarted:
    name: str


@dataclass(frozen=True)
class ReplyFinished:
    """Last event of a run. `text` is the authoritative final answer."""

    text: str


AgentEvent = Union[TextDelta, ToolStarted, ReplyFinished]


@runtime_checkable
class ChatUseCase(Protocol):
    def run(self, message: str) -> Iterator[AgentEvent]:
        """Answer a message: yield TextDelta and ToolStarted as they happen, then exactly one ReplyFinished."""

    def reply(self, message: str) -> str:
        """Answer a message and return only the final text."""


# --- Driven ports ---------------------------------------------------------


class LLMProvider(Protocol):
    def stream(self, system: str, messages: Sequence[Message], tools: Sequence[ToolSpec]) -> Iterator[LLMEvent]:
        """Run one model turn: yield TextDelta chunks as they arrive, then exactly one TurnComplete."""


class TicketRepository(Protocol):
    def create(self, title: str, description: str) -> Ticket:
        """Persist a new ticket and return it with its assigned id."""

    def list(self) -> List[Ticket]: ...


class FaqRepository(Protocol):
    def search(self, query: str) -> List[str]:
        """Return the answers whose topic appears in the query."""


class TicketNotifier(Protocol):
    def ticket_created(self, ticket: Ticket) -> bool:
        """Announce a new ticket. Returns whether the notification was delivered."""


class RateLimiter(Protocol):
    def hit(self, key: str) -> RateLimitDecision:
        """Count one request for `key` and say whether it fits in the current window."""
