import logging
from typing import Callable, Dict, Tuple

from app.application.conversation import ToolCall, ToolResult, ToolSpec
from app.application.ports import FaqRepository, TicketNotifier, TicketRepository

logger = logging.getLogger(__name__)

TOOL_FAILURE_MESSAGE = "Error: the tool failed due to a temporary problem; it did not complete."

TOOL_SPECS: Tuple[ToolSpec, ...] = (
    ToolSpec(
        name="search_faq",
        description="Search the FAQ for an answer. Use before creating a ticket.",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Keywords to search"}},
            "required": ["query"],
        },
    ),
    ToolSpec(
        name="create_ticket",
        description="Create a support ticket when the FAQ has no answer.",
        parameters={
            "type": "object",
            "properties": {"title": {"type": "string"}, "description": {"type": "string"}},
            "required": ["title", "description"],
        },
    ),
)


class SupportTools:
    """The tools the support agent can use, executed against the ports."""

    def __init__(self, faq: FaqRepository, tickets: TicketRepository, notifier: TicketNotifier):
        self._faq = faq
        self._tickets = tickets
        self._notifier = notifier
        self._handlers: Dict[str, Callable[..., str]] = {
            "search_faq": self._search_faq,
            "create_ticket": self._create_ticket,
        }

    @property
    def specs(self) -> Tuple[ToolSpec, ...]:
        return TOOL_SPECS

    def execute(self, call: ToolCall) -> ToolResult:
        handler = self._handlers.get(call.name)
        if handler is None:
            return ToolResult(call.id, "Error: unknown tool '%s'." % call.name, is_error=True)
        try:
            return ToolResult(call.id, handler(**call.arguments))
        except TypeError as exc:
            return ToolResult(call.id, "Error: invalid arguments (%s)." % exc, is_error=True)
        except Exception:  # an adapter failed (e.g. the database is down): let the model tell the user
            logger.exception("tool %s failed", call.name)
            return ToolResult(call.id, TOOL_FAILURE_MESSAGE, is_error=True)

    def _search_faq(self, query: str) -> str:
        hits = self._faq.search(query)
        return "\n".join(hits) if hits else "No FAQ entry found."

    def _create_ticket(self, title: str, description: str) -> str:
        ticket = self._tickets.create(title, description)
        try:
            self._notifier.ticket_created(ticket)
        except Exception as exc:  # notification is best-effort; the ticket already exists
            logger.warning("ticket notification failed: %s", exc)
        return "Ticket %s created." % ticket.id
