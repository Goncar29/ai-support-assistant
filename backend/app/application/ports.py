"""Ports: what the application needs from the outside world.

Adapters in `app.infrastructure` implement these protocols; the application
never imports an adapter directly.
"""
from typing import Iterator, List, Protocol, Sequence

from app.application.conversation import LLMEvent, Message, ToolSpec
from app.domain.ticket import Ticket


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
