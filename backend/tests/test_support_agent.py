from app.application.conversation import AssistantMessage, ToolCall, ToolResultsMessage, UserMessage
from app.application.support_agent import SupportAgent
from app.application.support_tools import SupportTools
from app.infrastructure.in_memory import DEFAULT_FAQ, InMemoryFaqRepository, InMemoryTicketRepository
from app.infrastructure.notifications import NullNotifier
from tests.fakes import ScriptedLLM


def make_agent(turns):
    llm = ScriptedLLM(turns)
    tools = SupportTools(InMemoryFaqRepository(DEFAULT_FAQ), InMemoryTicketRepository(), NullNotifier())
    return SupportAgent(llm, tools), llm


def search(call_id, query):
    return AssistantMessage(text="", tool_calls=(ToolCall(call_id, "search_faq", {"query": query}),))


def test_agent_runs_requested_tool_then_answers():
    agent, llm = make_agent([search("1", "refund"), AssistantMessage(text="Refunds take 5 days.")])

    assert agent.reply("refund?") == "Refunds take 5 days."

    second_turn = llm.calls[1]
    assert second_turn[0] == UserMessage("refund?")
    tool_results = second_turn[-1]
    assert isinstance(tool_results, ToolResultsMessage)
    assert tool_results.results[0].call_id == "1"
    assert "5 business days" in tool_results.results[0].content


def test_agent_offers_support_tools_to_the_model():
    agent, llm = make_agent([AssistantMessage(text="hi")])
    agent.reply("hello")
    assert [spec.name for spec in llm.tools[0]] == ["search_faq", "create_ticket"]


def test_agent_gives_up_after_max_steps():
    agent, llm = make_agent([search("x", "a")] * 10)
    assert "could not complete" in agent.reply("loop")
    assert len(llm.calls) == 5
