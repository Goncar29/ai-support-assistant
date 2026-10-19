from app.application.conversation import (
    STOP_MAX_TOKENS,
    STOP_REFUSAL,
    STOP_TOOL_USE,
    AssistantMessage,
    TextDelta,
    ToolCall,
    ToolResultsMessage,
    UserMessage,
)
from app.application.support_agent import GIVE_UP_REPLY, REFUSAL_REPLY, ReplyFinished, SupportAgent, ToolStarted
from app.application.support_tools import SupportTools
from app.infrastructure.in_memory import DEFAULT_FAQ, InMemoryFaqRepository, InMemoryTicketRepository
from app.infrastructure.notifications import NullNotifier
from tests.fakes import ScriptedLLM


def make_agent(turns):
    llm = ScriptedLLM(turns)
    tickets = InMemoryTicketRepository()
    tools = SupportTools(InMemoryFaqRepository(DEFAULT_FAQ), tickets, NullNotifier())
    return SupportAgent(llm, tools), llm, tickets


def call(call_id, name, args, text=""):
    return AssistantMessage(text=text, tool_calls=(ToolCall(call_id, name, args),), stop_reason=STOP_TOOL_USE)


def search(call_id, query, text=""):
    return call(call_id, "search_faq", {"query": query}, text)


def test_agent_runs_requested_tool_then_answers():
    agent, llm, _ = make_agent([search("1", "refund"), AssistantMessage(text="Refunds take 5 days.")])

    assert agent.reply("refund?") == "Refunds take 5 days."

    second_turn = llm.calls[1]
    assert second_turn[0] == UserMessage("refund?")
    tool_results = second_turn[-1]
    assert isinstance(tool_results, ToolResultsMessage)
    assert tool_results.results[0].call_id == "1"
    assert "5 business days" in tool_results.results[0].content


def test_run_streams_text_tool_activity_and_final_reply():
    agent, _, _ = make_agent([search("1", "refund", text="Let me check. "), AssistantMessage(text="5 days.")])

    events = list(agent.run("refund?"))

    assert events == [
        TextDelta("Let me check. "),
        ToolStarted("search_faq"),
        TextDelta("5 days."),
        ReplyFinished("5 days."),
    ]


def test_agent_offers_support_tools_to_the_model():
    agent, llm, _ = make_agent([AssistantMessage(text="hi")])
    agent.reply("hello")
    assert [spec.name for spec in llm.tools[0]] == ["search_faq", "create_ticket"]


def test_agent_gives_up_after_max_steps():
    agent, llm, _ = make_agent([search("x", "a")] * 10)
    assert "could not complete" in agent.reply("loop")
    assert len(llm.calls) == 5


def test_truncated_turn_never_runs_its_tools():
    truncated = AssistantMessage(
        text="Creating", tool_calls=(ToolCall("1", "create_ticket", {"title": "t"}),), stop_reason=STOP_MAX_TOKENS
    )
    agent, llm, tickets = make_agent([truncated])

    assert agent.reply("help") == "Creating"
    assert tickets.list() == []
    assert len(llm.calls) == 1


def test_truncated_turn_without_text_gets_a_fallback_reply():
    truncated = AssistantMessage(
        text="", tool_calls=(ToolCall("1", "create_ticket", {"title": "t"}),), stop_reason=STOP_MAX_TOKENS
    )
    agent, _, tickets = make_agent([truncated])
    assert agent.reply("help") == GIVE_UP_REPLY
    assert tickets.list() == []


def test_refusal_without_text_gets_a_polite_reply():
    agent, _, _ = make_agent([AssistantMessage(text="", stop_reason=STOP_REFUSAL)])
    assert agent.reply("something unsafe") == REFUSAL_REPLY
