"""In-memory adapters: local development and tests. State is lost on restart."""
from typing import Dict, List

from app.domain.ticket import Ticket

DEFAULT_FAQ: Dict[str, str] = {
    "refund": "Refunds are processed within 5 business days after approval.",
    "shipping": "Standard shipping takes 3-7 business days.",
    "password": "Use 'Forgot password' on the login page to reset it.",
}


class InMemoryFaqRepository:
    def __init__(self, entries: Dict[str, str]):
        self._entries = dict(entries)

    def search(self, query: str) -> List[str]:
        q = query.lower()
        return [answer for topic, answer in self._entries.items() if topic in q]


class InMemoryTicketRepository:
    def __init__(self) -> None:
        self._tickets: List[Ticket] = []

    def create(self, title: str, description: str) -> Ticket:
        ticket = Ticket("T-%04d" % (len(self._tickets) + 1), title, description)
        self._tickets.append(ticket)
        return ticket

    def list(self) -> List[Ticket]:
        return list(self._tickets)
