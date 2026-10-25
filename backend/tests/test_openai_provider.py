from types import SimpleNamespace as NS

import httpx2
import openai
import pytest
from openai.types.responses import (
    Response,
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputRefusal,
    ResponseOutputText,
    ResponseReasoningItem,
)

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
    ModelUnavailable,
    UserMessage,
)
from app.infrastructure.llm.openai_provider import OpenAIProvider


class FakeStream:
    """Raw Responses API events: text deltas, then the terminal event carrying the whole response."""

    def __init__(self, events):
        self.events = events

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def __iter__(self):
        return iter(self.events)


class FakeClient:
    def __init__(self, streams):
        self.streams = list(streams)
        self.calls = []
        self.responses = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeStream(self.streams.pop(0))


def message(*parts):
    return ResponseOutputMessage(id="msg_1", type="message", role="assistant", status="completed", content=list(parts))


def text(value):
    return ResponseOutputText(type="output_text", text=value, annotations=[])


def call(call_id, name, arguments):
    return ResponseFunctionToolCall(type="function_call", id="fc_" + call_id, call_id=call_id, name=name, arguments=arguments)


def response(*output, status="completed", incomplete_reason=None):
    details = NS(reason=incomplete_reason) if incomplete_reason else None
    return Response.model_construct(output=list(output), status=status, incomplete_details=details)


def stream_of(final, terminal="response.completed"):
    deltas = [
        NS(type="response.output_text.delta", delta=part.text)
        for item in final.output if item.type == "message"
        for part in item.content if part.type == "output_text"
    ]
    return [NS(type="response.created"), *deltas, NS(type=terminal, response=final)]


def run(provider, messages, tools=()):
    return list(provider.stream("sys", messages, list(tools)))


def test_translates_request_and_streams_text_then_the_complete_turn():
    final = response(message(text("Let me check.")), call("c1", "search_faq", '{"query": "refund"}'))
    client = FakeClient([stream_of(final)])
    provider = OpenAIProvider(client, model="test-model", max_output_tokens=512)

    events = run(provider, [UserMessage("hi")], [ToolSpec("search_faq", "desc", {"type": "object"})])

    request = client.calls[0]
    assert request["model"] == "test-model"
    assert request["instructions"] == "sys"
    assert request["input"] == [{"role": "user", "content": "hi"}]
    assert request["max_output_tokens"] == 512
    assert request["stream"] is True
    # Conversations stay off OpenAI's servers; reasoning comes back encrypted so the next step can replay it.
    assert request["store"] is False
    assert request["include"] == ["reasoning.encrypted_content"]
    # strict is required by the SDK type; our schemas (maxLength, no additionalProperties) are not strict-compatible.
    assert request["tools"] == [
        {"type": "function", "name": "search_faq", "description": "desc", "parameters": {"type": "object"}, "strict": False}
    ]
    assert events[0] == TextDelta("Let me check.")
    assert isinstance(events[-1], TurnComplete)
    turn = events[-1].message
    assert turn.text == "Let me check."
    assert turn.tool_calls == (ToolCall("c1", "search_faq", {"query": "refund"}),)
    assert turn.stop_reason == STOP_TOOL_USE


def test_defaults_cap_each_step_at_4000_output_tokens():
    client = FakeClient([stream_of(response(message(text("ok"))))])
    run(OpenAIProvider(client, model="m"), [UserMessage("hi")])
    assert client.calls[0]["max_output_tokens"] == 4000
    assert "tools" not in client.calls[0]


def test_plain_answer_ends_the_turn():
    turn = run(OpenAIProvider(FakeClient([stream_of(response(message(text("Done."))))]), model="m"), [UserMessage("hi")])
    assert turn[-1].message.stop_reason == STOP_END
    assert turn[-1].message.text == "Done."


@pytest.mark.parametrize("reason, neutral", [
    ("max_output_tokens", STOP_MAX_TOKENS),
    ("content_filter", STOP_REFUSAL),
])
def test_maps_incomplete_responses(reason, neutral):
    # A cut-off turn arrives as response.incomplete, never response.completed.
    final = response(message(text("Partial")), status="incomplete", incomplete_reason=reason)
    client = FakeClient([stream_of(final, terminal="response.incomplete")])

    turn = run(OpenAIProvider(client, model="m"), [UserMessage("hi")])[-1].message

    assert turn.stop_reason == neutral
    assert turn.text == "Partial"


def test_refusal_part_is_a_refusal():
    final = response(message(ResponseOutputRefusal(type="refusal", refusal="I can't help with that.")))
    turn = run(OpenAIProvider(FakeClient([stream_of(final)]), model="m"), [UserMessage("hi")])[-1].message
    assert turn.stop_reason == STOP_REFUSAL
    assert turn.text == ""


def test_unparseable_arguments_become_empty_so_the_tool_reports_the_error():
    final = response(call("c1", "search_faq", '{"query": "ref'))
    turn = run(OpenAIProvider(FakeClient([stream_of(final)]), model="m"), [UserMessage("hi")])[-1].message
    assert turn.tool_calls == (ToolCall("c1", "search_faq", {}),)


def test_failed_response_raises_with_its_error():
    final = Response.model_construct(output=[], status="failed", error=NS(code="invalid_prompt", message="boom"))
    with pytest.raises(RuntimeError, match="boom"):
        run(OpenAIProvider(FakeClient([stream_of(final, terminal="response.failed")]), model="m"), [UserMessage("hi")])


def test_stream_without_a_final_response_raises():
    with pytest.raises(RuntimeError, match="ended before"):
        run(OpenAIProvider(FakeClient([[NS(type="response.created")]]), model="m"), [UserMessage("hi")])


def test_replays_native_output_items_including_reasoning_and_sends_tool_outputs():
    reasoning = ResponseReasoningItem(id="rs_1", type="reasoning", summary=[], encrypted_content="enc")
    first = response(reasoning, call("c1", "search_faq", '{"query": "a"}'))
    client = FakeClient([stream_of(first), stream_of(response(message(text("ok"))))])
    provider = OpenAIProvider(client, model="m")

    turn = run(provider, [UserMessage("hi")])[-1].message
    run(provider, [UserMessage("hi"), turn, ToolResultsMessage((ToolResult("c1", "found"), ToolResult("c2", "Error: boom", is_error=True)))])

    assert client.calls[1]["input"] == [
        {"role": "user", "content": "hi"},
        {"id": "rs_1", "type": "reasoning", "summary": [], "encrypted_content": "enc"},
        {"type": "function_call", "id": "fc_c1", "call_id": "c1", "name": "search_faq", "arguments": '{"query": "a"}'},
        {"type": "function_call_output", "call_id": "c1", "output": "found"},
        {"type": "function_call_output", "call_id": "c2", "output": "Error: boom"},
    ]


def test_rebuilds_assistant_turns_from_other_providers():
    client = FakeClient([stream_of(response(message(text("ok"))))])
    history = [UserMessage("hi"), AssistantMessage("Checking.", (ToolCall("c1", "search_faq", {"query": "a"}),))]

    run(OpenAIProvider(client, model="m"), history)

    assert client.calls[0]["input"][1:] == [
        {"role": "assistant", "content": "Checking."},
        {"type": "function_call", "call_id": "c1", "name": "search_faq", "arguments": '{"query": "a"}'},
    ]


class FailingClient:
    def __init__(self, error):
        self.error = error
        self.responses = self

    def create(self, **kwargs):
        raise self.error


def _status_error(cls, status):
    return cls("upstream says no", response=httpx2.Response(status, request=httpx2.Request("POST", "https://api.test")), body=None)


@pytest.mark.parametrize("error", [
    _status_error(openai.RateLimitError, 429),
    _status_error(openai.InternalServerError, 503),
    openai.APITimeoutError(request=httpx2.Request("POST", "https://api.test")),
    openai.APIConnectionError(request=httpx2.Request("POST", "https://api.test")),
])
def test_transient_failures_become_model_unavailable(error):
    with pytest.raises(ModelUnavailable):
        run(OpenAIProvider(FailingClient(error), model="m"), [UserMessage("hi")])


def test_other_api_errors_pass_through():
    error = _status_error(openai.AuthenticationError, 401)
    with pytest.raises(openai.AuthenticationError):
        run(OpenAIProvider(FailingClient(error), model="m"), [UserMessage("hi")])


def test_failed_response_from_overload_is_model_unavailable():
    final = Response.model_construct(output=[], status="failed", error=NS(code="server_error", message="busy"))
    with pytest.raises(ModelUnavailable):
        run(OpenAIProvider(FakeClient([stream_of(final, terminal="response.failed")]), model="m"), [UserMessage("hi")])
