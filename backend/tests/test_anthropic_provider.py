from types import SimpleNamespace as NS

import pytest

from app.application.conversation import (
    STOP_END,
    STOP_MAX_TOKENS,
    STOP_REFUSAL,
    STOP_TOOL_USE,
    AssistantMessage,
    TextDelta,
    ToolCall,
    ToolResult,
    ToolResultsMessage,
    ToolSpec,
    TurnComplete,
    UserMessage,
)
from app.infrastructure.llm.anthropic_provider import AnthropicProvider


class FakeStream:
    def __init__(self, final):
        self.final = final

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def __iter__(self):
        return iter([NS(type="text", text=b.text) for b in self.final.content if b.type == "text"])

    def get_final_message(self):
        return self.final


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.messages = self

    def stream(self, **kwargs):
        self.calls.append(kwargs)
        return FakeStream(self.responses.pop(0))


def done(text="ok", stop_reason="end_turn"):
    return NS(stop_reason=stop_reason, content=[NS(type="text", text=text)])


def run(provider, messages, tools=()):
    return list(provider.stream("sys", messages, list(tools)))


def test_translates_request_and_streams_text_then_the_complete_turn():
    client = FakeClient([NS(stop_reason="tool_use", content=[
        NS(type="text", text="Let me check."),
        NS(type="tool_use", id="1", name="search_faq", input={"query": "refund"}),
    ])])
    provider = AnthropicProvider(client, model="test-model", max_tokens=512)

    events = run(provider, [UserMessage("hi")], [ToolSpec("search_faq", "desc", {"type": "object"})])

    request = client.calls[0]
    assert request["model"] == "test-model"
    assert request["max_tokens"] == 512
    assert request["output_config"] == {"effort": "low"}
    assert request["system"] == "sys"
    assert request["messages"] == [{"role": "user", "content": "hi"}]
    assert request["tools"] == [{"name": "search_faq", "description": "desc", "input_schema": {"type": "object"}}]
    assert events[0] == TextDelta("Let me check.")
    turn = events[-1].message
    assert isinstance(events[-1], TurnComplete)
    assert turn.text == "Let me check."
    assert turn.tool_calls == (ToolCall("1", "search_faq", {"query": "refund"}),)
    assert turn.stop_reason == STOP_TOOL_USE


def test_defaults_leave_room_for_thinking_at_low_effort():
    client = FakeClient([done()])
    run(AnthropicProvider(client, model="m"), [UserMessage("hi")])
    assert client.calls[0]["max_tokens"] == 16000
    assert client.calls[0]["output_config"] == {"effort": "low"}


@pytest.mark.parametrize("native, neutral", [
    ("end_turn", STOP_END),
    ("stop_sequence", STOP_END),
    ("max_tokens", STOP_MAX_TOKENS),
    ("refusal", STOP_REFUSAL),
])
def test_maps_stop_reasons(native, neutral):
    client = FakeClient([done(stop_reason=native)])
    assert run(AnthropicProvider(client, model="m"), [UserMessage("hi")])[-1].message.stop_reason == neutral


def test_ignores_thinking_blocks_in_text_but_replays_them():
    thinking = NS(type="thinking", thinking="", signature="sig")
    client = FakeClient([NS(stop_reason="end_turn", content=[thinking, NS(type="text", text="Answer")])])

    turn = run(AnthropicProvider(client, model="m"), [UserMessage("hi")])[-1].message

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

    run(AnthropicProvider(client, model="m", effort="high"), history)

    assert client.calls[0]["output_config"] == {"effort": "high"}
    messages = client.calls[0]["messages"]
    assert messages[1] == {"role": "assistant", "content": native}
    assert messages[2] == {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "1", "content": "found", "is_error": False},
        {"type": "tool_result", "tool_use_id": "2", "content": "boom", "is_error": True},
    ]}
    assert "tools" not in client.calls[0]
