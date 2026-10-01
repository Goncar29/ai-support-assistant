from types import SimpleNamespace as NS

from app.llm import generate_reply
from app.tools import TICKETS, execute_tool


def text(t):
    return NS(type="text", text=t)


def tool_use(id_, name, input_):
    return NS(type="tool_use", id=id_, name=name, input=input_)


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def test_agent_calls_tool_then_answers():
    client = FakeClient([
        NS(stop_reason="tool_use", content=[tool_use("1", "search_faq", {"query": "refund"})]),
        NS(stop_reason="end_turn", content=[text("Refunds take 5 days.")]),
    ])
    assert generate_reply("refund?", client=client) == "Refunds take 5 days."
    result = client.calls[1]["messages"][-1]["content"][0]
    assert result["tool_use_id"] == "1"
    assert "5 business days" in result["content"]


def test_agent_stops_after_max_steps():
    looping = NS(stop_reason="tool_use", content=[tool_use("x", "search_faq", {"query": "a"})])
    client = FakeClient([looping] * 10)
    assert "could not complete" in generate_reply("loop", client=client)
    assert len(client.calls) == 5


def test_create_ticket_stores_ticket():
    TICKETS.clear()
    out = execute_tool("create_ticket", {"title": "t", "description": "d"})
    assert out == "Ticket T-0001 created."
    assert len(TICKETS) == 1


def test_unknown_tool_and_bad_args_return_errors():
    assert "unknown tool" in execute_tool("nope", {})
    assert "invalid arguments" in execute_tool("search_faq", {"wrong": 1})
