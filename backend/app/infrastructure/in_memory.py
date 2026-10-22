"""In-memory adapters: local development and tests. State is lost on restart."""
import threading
import time
import unicodedata
from typing import Callable, Dict, List, Optional

from app.domain.rate_limit import RateLimitDecision, current_window, decide
from app.domain.ticket import Ticket

DEFAULT_FAQ: Dict[str, str] = {
    "refund": "Refunds are processed within 5 business days after approval.",
    "shipping": "Standard shipping takes 3-7 business days.",
    "password": "Use 'Forgot password' on the login page to reset it.",
    # Spanish entries; topics are written without accents because search ignores them.
    "reembolso": "Los reembolsos se procesan dentro de los 5 días hábiles posteriores a su aprobación.",
    "envio": "El envío estándar tarda de 3 a 7 días hábiles.",
    "contrasena": "Usa 'Olvidé mi contraseña' en la página de inicio de sesión para restablecerla.",
}


def _fold(text: str) -> str:
    """Lowercase and strip accents, so "Envío" and "envio" match the same topic."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


class InMemoryFaqRepository:
    def __init__(self, entries: Dict[str, str]):
        self._entries = dict(entries)

    def search(self, query: str) -> List[str]:
        q = _fold(query)
        return [answer for topic, answer in self._entries.items() if _fold(topic) in q]


class InMemoryTicketRepository:
    def __init__(self) -> None:
        self._tickets: List[Ticket] = []

    def create(self, title: str, description: str) -> Ticket:
        ticket = Ticket("T-%04d" % (len(self._tickets) + 1), title, description)
        self._tickets.append(ticket)
        return ticket

    def list(self) -> List[Ticket]:
        return list(self._tickets)


class InMemoryRateLimiter:
    """Counts per process. On serverless each instance has its own counts, so production uses Postgres."""

    def __init__(self, limit: int, window_seconds: int, clock: Callable[[], float] = time.time):
        self._limit = limit
        self._window_seconds = window_seconds
        self._clock = clock
        self._lock = threading.Lock()  # sync FastAPI routes run in a thread pool
        self._window_start: Optional[int] = None
        self._counts: Dict[str, int] = {}

    def hit(self, key: str) -> RateLimitDecision:
        start, retry_after = current_window(self._clock(), self._window_seconds)
        with self._lock:
            if start != self._window_start:  # new window: forget the old counts, so memory stays bounded
                self._window_start = start
                self._counts = {}
            self._counts[key] = self._counts.get(key, 0) + 1
            count = self._counts[key]
        return decide(count, self._limit, retry_after)
