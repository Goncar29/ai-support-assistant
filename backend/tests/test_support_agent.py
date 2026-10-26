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
from app.application.ports import ChatUseCase, ReplyFinished, ToolStarted
from app.application.support_agent import GIVE_UP_REPLY, MAX_HISTORY_CHARS, REFUSAL_REPLY, SupportAgent
from app.application.support_tools import TICKET_LIMIT_MESSAGE, SupportTools
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


def test_agent_tells_the_model_to_answer_only_from_the_faq():
    agent, llm, _ = make_agent([search("1", "shipping"), AssistantMessage(text="3-7 days.")])
    agent.reply("Does international shipping take longer?")

    # Every step gets the same rules, so a later turn cannot drift from them.
    assert len(llm.systems) == 2
    for system in llm.systems:
        assert "Reply in the language of the user's latest message" in system
        assert "Do not add facts, numbers or cases the FAQ does not state" in system
        assert "Create a ticket only if no answer is found" in system


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


def test_support_agent_implements_the_chat_port():
    agent, _, _ = make_agent([AssistantMessage("hi")])
    assert isinstance(agent, ChatUseCase)


def ticket(call_id, title="t"):
    return call(call_id, "create_ticket", {"title": title, "description": "d"})


def tool_result(llm, turn):
    return llm.calls[turn][-1].results


def test_a_request_creates_at_most_one_ticket_across_steps():
    agent, llm, tickets = make_agent([ticket("1", "a"), ticket("2", "b"), AssistantMessage(text="Done.")])

    assert agent.reply("help") == "Done."

    assert [t.title for t in tickets.list()] == ["a"]
    [rejected] = tool_result(llm, 2)
    assert rejected.is_error
    assert rejected.content == TICKET_LIMIT_MESSAGE


def test_a_second_ticket_in_the_same_turn_is_rejected():
    two = AssistantMessage(
        text="",
        tool_calls=(
            ToolCall("1", "create_ticket", {"title": "a", "description": "d"}),
            ToolCall("2", "create_ticket", {"title": "b", "description": "d"}),
        ),
        stop_reason=STOP_TOOL_USE,
    )
    agent, llm, tickets = make_agent([two, AssistantMessage(text="Done.")])

    agent.reply("help")

    assert len(tickets.list()) == 1
    first, second = tool_result(llm, 1)
    assert not first.is_error and second.is_error


def test_the_ticket_budget_is_per_request():
    agent, _, tickets = make_agent([ticket("1"), AssistantMessage(text="One."), ticket("2"), AssistantMessage(text="Two.")])

    agent.reply("first request")
    agent.reply("second request")

    assert len(tickets.list()) == 2


def test_history_goes_before_the_new_message():
    agent, llm, _ = make_agent([AssistantMessage(text="About 5 days.")])
    history = [UserMessage("I want a refund"), AssistantMessage("Refunds take 5 business days.")]

    agent.reply("And when does it start?", history)

    assert llm.calls[0] == [*history, UserMessage("And when does it start?")]


def test_history_keeps_only_the_most_recent_messages_within_the_budget():
    agent, llm, _ = make_agent([AssistantMessage(text="ok")])
    old = [UserMessage("u%d " % i + "x" * 1000) if i % 2 == 0 else AssistantMessage("a%d " % i + "x" * 1000) for i in range(20)]

    agent.reply("latest", old)

    context = llm.calls[0][:-1]
    assert sum(len(m.text) for m in context) <= MAX_HISTORY_CHARS
    assert context[-1] == old[-1]  # the newest history survives
    assert isinstance(context[0], UserMessage)  # and the context still opens with the user


def test_history_is_cleaned_for_providers_that_need_alternating_turns():
    agent, llm, _ = make_agent([AssistantMessage(text="ok")])
    # A leading assistant turn is dropped; a user turn left without a reply joins the next one.
    history = [AssistantMessage("Welcome!"), UserMessage("first"), AssistantMessage("reply"), UserMessage("unanswered")]

    agent.reply("again", history)

    assert llm.calls[0] == [UserMessage("first"), AssistantMessage("reply"), UserMessage("unanswered\n\nagain")]
