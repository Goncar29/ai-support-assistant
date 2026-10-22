from app.application.conversation import ToolCall, ToolResult
import pytest

from app.application.support_tools import TOOL_FAILURE_MESSAGE, TOOL_SPECS, SupportTools
from app.domain.ticket import DESCRIPTION_MAX_LENGTH, TITLE_MAX_LENGTH, Ticket
from app.infrastructure.in_memory import DEFAULT_FAQ, InMemoryFaqRepository, InMemoryTicketRepository
from tests.fakes import FailingTicketRepository, RecordingNotifier


def make_tools(notifier=None):
    tickets = InMemoryTicketRepository()
    tools = SupportTools(InMemoryFaqRepository(DEFAULT_FAQ), tickets, notifier or RecordingNotifier())
    return tools, tickets


def test_create_ticket_stores_and_notifies():
    notifier = RecordingNotifier()
    tools, tickets = make_tools(notifier)

    result = tools.execute(ToolCall("1", "create_ticket", {"title": "t", "description": "d"}))

    assert result == ToolResult("1", "Ticket T-0001 created.")
    assert tickets.list() == [Ticket("T-0001", "t", "d")]
    assert notifier.sent == [Ticket("T-0001", "t", "d")]


def test_notifier_failure_does_not_break_ticket_creation():
    tools, tickets = make_tools(RecordingNotifier(fail=True))
    result = tools.execute(ToolCall("1", "create_ticket", {"title": "t", "description": "d"}))
    assert result.content == "Ticket T-0001 created."
    assert not result.is_error
    assert len(tickets.list()) == 1


def test_search_faq_returns_matches_or_a_miss():
    tools, _ = make_tools()
    assert "5 business days" in tools.execute(ToolCall("1", "search_faq", {"query": "Refund status"})).content
    assert tools.execute(ToolCall("2", "search_faq", {"query": "pizza"})).content == "No FAQ entry found."


def test_unknown_tool_and_bad_arguments_are_errors():
    tools, _ = make_tools()
    unknown = tools.execute(ToolCall("1", "nope", {}))
    bad_args = tools.execute(ToolCall("2", "search_faq", {"wrong": 1}))
    assert unknown.is_error and "unknown tool" in unknown.content
    assert bad_args.is_error and "invalid arguments" in bad_args.content


def test_storage_failure_becomes_a_tool_error_the_model_can_explain():
    notifier = RecordingNotifier()
    tools = SupportTools(InMemoryFaqRepository(DEFAULT_FAQ), FailingTicketRepository(), notifier)

    result = tools.execute(ToolCall("1", "create_ticket", {"title": "t", "description": "d"}))

    assert result == ToolResult("1", TOOL_FAILURE_MESSAGE, is_error=True)
    assert notifier.sent == []


def test_create_ticket_schema_caps_field_lengths():
    spec = next(s for s in TOOL_SPECS if s.name == "create_ticket")
    properties = spec.parameters["properties"]
    assert properties["title"]["maxLength"] == TITLE_MAX_LENGTH == 120
    assert properties["description"]["maxLength"] == DESCRIPTION_MAX_LENGTH == 2000


@pytest.mark.parametrize("field, limit", [("title", TITLE_MAX_LENGTH), ("description", DESCRIPTION_MAX_LENGTH)])
def test_oversized_ticket_fields_are_rejected_without_storing_or_notifying(field, limit):
    notifier = RecordingNotifier()
    tools, tickets = make_tools(notifier)
    arguments = {"title": "t", "description": "d", field: "x" * (limit + 1)}

    result = tools.execute(ToolCall("1", "create_ticket", arguments))

    assert result.is_error
    assert result.content == "Error: invalid arguments (%s must be at most %d characters)." % (field, limit)
    assert tickets.list() == []
    assert notifier.sent == []


def test_ticket_fields_at_the_limit_are_accepted():
    tools, tickets = make_tools()
    title, description = "t" * TITLE_MAX_LENGTH, "d" * DESCRIPTION_MAX_LENGTH
    result = tools.execute(ToolCall("1", "create_ticket", {"title": title, "description": description}))
    assert not result.is_error
    assert tickets.list() == [Ticket("T-0001", title, description)]
