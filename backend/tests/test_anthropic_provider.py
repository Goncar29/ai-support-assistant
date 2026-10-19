from types import SimpleNamespace as NS

from app.application.conversation import (
    AssistantMessage,
    ToolCall,
    ToolResult,
    ToolResultsMessage,
    ToolSpec,
    UserMessage,
)
from app.infrastructure.llm.anthropic_provider import AnthropicProvider


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def done(text="ok"):
    return NS(stop_reason="end_turn", content=[NS(type="text", text=text)])


def test_translates_request_and_parses_tool_calls():
    client = FakeClient([NS(stop_reason="tool_use", content=[
        NS(type="text", text="Let me check."),
        NS(type="tool_use", id="1", name="search_faq", input={"query": "refund"}),
    ])])
    provider = AnthropicProvider(client, model="test-model", max_tokens=512)

    turn = provider.complete("sys", [UserMessage("hi")], [ToolSpec("search_faq", "desc", {"type": "object"})])

    request = client.calls[0]
    assert request["model"] == "test-model"
    assert request["max_tokens"] == 512
    assert request["output_config"] == {"effort": "low"}
    assert request["system"] == "sys"
    assert request["messages"] == [{"role": "user", "content": "hi"}]
    assert request["tools"] == [{"name": "search_faq", "description": "desc", "input_schema": {"type": "object"}}]
    assert turn.text == "Let me check."
    assert turn.tool_calls == (ToolCall("1", "search_faq", {"query": "refund"}),)


def test_ignores_thinking_blocks_in_text_but_replays_them():
    thinking = NS(type="thinking", thinking="", signature="sig")
    client = FakeClient([NS(stop_reason="end_turn", content=[thinking, NS(type="text", text="Answer")])])

    turn = AnthropicProvider(client, model="m").complete("sys", [UserMessage("hi")], [])

    assert turn.text == "Answer"
    assert turn.provider_payload[0] is thinking


def test_replays_native_assistant_content_and_tool_results():
    client = FakeClient([done()])
    native = [NS(type="tool_use", id="1", name="search_faq", input={"query": "a"})]
    history = [
        UserMessage("hi"),
        AssistantMessage("", (ToolCall("1", "search_faq", {"query": "a"}),), provider_payload=native),
        ToolResultsMessage((ToolResult("1", "found"), ToolResult("2", "boom", is_error=True))),
    ]

    AnthropicProvider(client, model="m", effort="high").complete("sys", history, [])

    assert client.calls[0]["output_config"] == {"effort": "high"}

    messages = client.calls[0]["messages"]
    assert messages[1] == {"role": "assistant", "content": native}
    assert messages[2] == {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "1", "content": "found", "is_error": False},
        {"type": "tool_result", "tool_use_id": "2", "content": "boom", "is_error": True},
    ]}
    assert "tools" not in client.calls[0]
