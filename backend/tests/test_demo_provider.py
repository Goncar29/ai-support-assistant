from app.application.ports import ReplyFinished, ToolStarted
from app.application.conversation import TextDelta
from app.application.support_agent import SupportAgent
from app.application.support_tools import SupportTools
from app.domain.ticket import DESCRIPTION_MAX_LENGTH, Ticket
from app.infrastructure.in_memory import DEFAULT_FAQ, InMemoryFaqRepository, InMemoryTicketRepository
from app.infrastructure.llm.demo_provider import DEMO_PREFIX, DemoProvider
from tests.fakes import FailingTicketRepository, RecordingNotifier


def run_demo(message, tickets=None):
    tickets = tickets if tickets is not None else InMemoryTicketRepository()
    tools = SupportTools(InMemoryFaqRepository(DEFAULT_FAQ), tickets, RecordingNotifier())
    events = list(SupportAgent(DemoProvider(), tools).run(message))
    tools_used = [e.name for e in events if isinstance(e, ToolStarted)]
    streamed = "".join(e.text for e in events if isinstance(e, TextDelta))
    final = events[-1]
    assert isinstance(final, ReplyFinished)
    assert streamed == final.text  # the reply is streamed, not sent in one block
    return tools_used, final.text, tickets


def test_faq_question_is_answered_from_the_faq():
    tools_used, reply, tickets = run_demo("How long does shipping take?")
    assert tools_used == ["search_faq"]
    assert reply == DEMO_PREFIX + "Standard shipping takes 3-7 business days."
    assert tickets.list() == []


def test_unknown_question_suggests_topics_without_creating_a_ticket():
    tools_used, reply, tickets = run_demo("My order arrived broken")
    assert tools_used == ["search_faq"]
    assert reply.startswith(DEMO_PREFIX)
    assert "refunds, shipping or passwords" in reply
    assert "ticket" in reply  # tells the user how to get a ticket
    assert tickets.list() == []


def test_explicit_request_creates_a_ticket():
    message = "Please open a ticket: my order arrived broken"
    tools_used, reply, tickets = run_demo(message)
    assert tools_used == ["search_faq", "create_ticket"]
    assert reply == DEMO_PREFIX + "I opened ticket T-0001 for you. Our team will get back to you soon."
    assert tickets.list() == [Ticket("T-0001", message, message)]


def test_ticket_request_in_spanish_is_understood():
    tools_used, _, tickets = run_demo("Quiero hablar con un humano")
    assert tools_used == ["search_faq", "create_ticket"]
    assert len(tickets.list()) == 1


def test_long_messages_fit_the_ticket_limits():
    message = "ticket " + "x" * 3000
    _, reply, tickets = run_demo(message)
    [ticket] = tickets.list()
    assert ticket.title == message[:60]
    assert ticket.description == message[:DESCRIPTION_MAX_LENGTH]
    assert "T-0001" in reply


def test_a_failed_ticket_is_reported_honestly():
    tools_used, reply, _ = run_demo("open a ticket please", tickets=FailingTicketRepository())
    assert tools_used == ["search_faq", "create_ticket"]
    assert reply == DEMO_PREFIX + "Sorry, I could not open the ticket right now. Please try again later."
