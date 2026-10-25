import httpx
import pytest
from google.genai import errors, types

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
from app.infrastructure.llm.gemini_provider import GeminiProvider


class FakeClient:
    def __init__(self, streams):
        self.streams = list(streams)
        self.calls = []
        self.models = self

    def generate_content_stream(self, **kwargs):
        self.calls.append(kwargs)
        return iter(self.streams.pop(0))


def chunk(*parts, finish_reason=None):
    return types.GenerateContentResponse(candidates=[
        types.Candidate(content=types.Content(role="model", parts=list(parts)), finish_reason=finish_reason)
    ])


def text(value, thought=None):
    return types.Part(text=value, thought=thought)


def call(name, args, call_id=None, signature=None):
    return types.Part(function_call=types.FunctionCall(id=call_id, name=name, args=args), thought_signature=signature)


def run(provider, messages, tools=()):
    return list(provider.stream("sys", messages, list(tools)))


def test_translates_request_and_streams_text_then_the_complete_turn():
    client = FakeClient([[
        chunk(text("Let me ")),
        chunk(text("check."), call("search_faq", {"query": "refund"}, call_id="c1"), finish_reason="STOP"),
    ]])
    provider = GeminiProvider(client, model="test-model", max_output_tokens=512)

    events = run(provider, [UserMessage("hi")], [ToolSpec("search_faq", "desc", {"type": "object"})])

    request = client.calls[0]
    assert request["model"] == "test-model"
    assert request["contents"] == [{"role": "user", "parts": [{"text": "hi"}]}]
    assert request["config"] == {
        "system_instruction": "sys",
        "max_output_tokens": 512,
        "automatic_function_calling": {"disable": True},
        "tools": [{"function_declarations": [
            {"name": "search_faq", "description": "desc", "parameters_json_schema": {"type": "object"}}
        ]}],
    }
    assert events[:2] == [TextDelta("Let me "), TextDelta("check.")]
    assert isinstance(events[-1], TurnComplete)
    turn = events[-1].message
    assert turn.text == "Let me check."
    assert turn.tool_calls == (ToolCall("c1", "search_faq", {"query": "refund"}),)
    assert turn.stop_reason == STOP_TOOL_USE


def test_request_is_valid_for_the_sdk():
    client = FakeClient([[chunk(text("ok"), finish_reason="STOP")]])
    history = [
        UserMessage("hi"),
        AssistantMessage("", (ToolCall("c1", "search_faq", {"query": "a"}),)),
        ToolResultsMessage((ToolResult("c1", "found"),)),
    ]
    run(GeminiProvider(client, model="m"), history, [ToolSpec("search_faq", "desc", {"type": "object"})])

    types.GenerateContentConfig.model_validate(client.calls[0]["config"])
    for content in client.calls[0]["contents"]:
        types.Content.model_validate(content)


def test_defaults_cap_each_step_at_4000_output_tokens():
    client = FakeClient([[chunk(text("ok"), finish_reason="STOP")]])
    run(GeminiProvider(client, model="m"), [UserMessage("hi")])
    assert client.calls[0]["config"]["max_output_tokens"] == 4000
    assert "tools" not in client.calls[0]["config"]


@pytest.mark.parametrize("native, neutral", [
    ("STOP", STOP_END),
    ("MAX_TOKENS", STOP_MAX_TOKENS),
    ("SAFETY", STOP_REFUSAL),
    ("PROHIBITED_CONTENT", STOP_REFUSAL),
    ("RECITATION", STOP_REFUSAL),
    ("MALFORMED_FUNCTION_CALL", STOP_END),
])
def test_maps_finish_reasons(native, neutral):
    client = FakeClient([[chunk(text("ok"), finish_reason=native)]])
    assert run(GeminiProvider(client, model="m"), [UserMessage("hi")])[-1].message.stop_reason == neutral


def test_cut_off_tool_call_is_not_tool_use():
    client = FakeClient([[chunk(call("search_faq", {"query": "a"}, call_id="c1"), finish_reason="MAX_TOKENS")]])
    assert run(GeminiProvider(client, model="m"), [UserMessage("hi")])[-1].message.stop_reason == STOP_MAX_TOKENS


def test_blocked_prompt_is_a_refusal():
    blocked = types.GenerateContentResponse(prompt_feedback=types.GenerateContentResponsePromptFeedback(block_reason="SAFETY"))
    turn = run(GeminiProvider(FakeClient([[blocked]]), model="m"), [UserMessage("hi")])[-1].message
    assert turn.stop_reason == STOP_REFUSAL
    assert turn.text == ""


def test_thoughts_are_not_streamed_or_part_of_the_answer():
    client = FakeClient([[chunk(text("thinking...", thought=True), text("Answer"), finish_reason="STOP")]])
    events = run(GeminiProvider(client, model="m"), [UserMessage("hi")])
    assert events[0] == TextDelta("Answer")
    assert events[-1].message.text == "Answer"


def test_replays_native_parts_with_their_thought_signatures_and_names_tool_results():
    signed = call("search_faq", {"query": "a"}, call_id="c1", signature=b"sig")
    client = FakeClient([[chunk(signed, finish_reason="STOP")], [chunk(text("ok"), finish_reason="STOP")]])
    provider = GeminiProvider(client, model="m")

    turn = run(provider, [UserMessage("hi")])[-1].message
    run(provider, [UserMessage("hi"), turn, ToolResultsMessage((ToolResult("c1", "found"),))])

    contents = client.calls[1]["contents"]
    assert contents[1]["role"] == "model"
    assert contents[1]["parts"][0] is signed
    assert contents[2] == {"role": "user", "parts": [
        {"function_response": {"id": "c1", "name": "search_faq", "response": {"result": "found"}}}
    ]}


def test_errors_go_back_under_the_error_key():
    client = FakeClient([[chunk(text("ok"), finish_reason="STOP")]])
    history = [
        UserMessage("hi"),
        AssistantMessage("", (ToolCall("c1", "create_ticket", {}),)),
        ToolResultsMessage((ToolResult("c1", "Error: boom", is_error=True),)),
    ]
    run(GeminiProvider(client, model="m"), history)
    assert client.calls[0]["contents"][2]["parts"][0]["function_response"]["response"] == {"error": "Error: boom"}


def test_calls_without_an_id_get_a_local_one_that_is_never_sent_back():
    client = FakeClient([[chunk(call("search_faq", {"query": "a"}), finish_reason="STOP")], [chunk(text("ok"), finish_reason="STOP")]])
    provider = GeminiProvider(client, model="m")

    turn = run(provider, [UserMessage("hi")])[-1].message
    (local_call,) = turn.tool_calls
    run(provider, [UserMessage("hi"), turn, ToolResultsMessage((ToolResult(local_call.id, "found"),))])

    assert local_call.id
    assert client.calls[1]["contents"][2]["parts"][0]["function_response"] == {
        "name": "search_faq", "response": {"result": "found"}
    }


def test_rebuilds_assistant_turns_from_other_providers():
    client = FakeClient([[chunk(text("ok"), finish_reason="STOP")]])
    history = [UserMessage("hi"), AssistantMessage("Checking.", (ToolCall("c1", "search_faq", {"query": "a"}),))]

    run(GeminiProvider(client, model="m"), history)

    assert client.calls[0]["contents"][1] == {"role": "model", "parts": [
        {"text": "Checking."},
        {"function_call": {"id": "c1", "name": "search_faq", "args": {"query": "a"}}},
    ]}


class FailingClient:
    def __init__(self, error):
        self.error = error
        self.models = self

    def generate_content_stream(self, **kwargs):
        raise self.error


@pytest.mark.parametrize("error", [
    errors.ServerError(503, {"error": {"code": 503, "message": "high demand", "status": "UNAVAILABLE"}}),
    errors.ClientError(429, {"error": {"code": 429, "message": "quota", "status": "RESOURCE_EXHAUSTED"}}),
    httpx.ReadTimeout("timed out"),
    httpx.ConnectError("unreachable"),
])
def test_transient_failures_become_model_unavailable(error):
    with pytest.raises(ModelUnavailable):
        run(GeminiProvider(FailingClient(error), model="m"), [UserMessage("hi")])


def test_other_api_errors_pass_through():
    error = errors.ClientError(400, {"error": {"code": 400, "message": "bad request", "status": "INVALID_ARGUMENT"}})
    with pytest.raises(errors.ClientError):
        run(GeminiProvider(FailingClient(error), model="m"), [UserMessage("hi")])


def test_a_failure_mid_stream_is_translated_too():
    def chunks():
        yield chunk(text("Partial"))
        raise httpx.ReadTimeout("timed out")

    client = FakeClient([chunks()])
    events = []
    with pytest.raises(ModelUnavailable):
        for event in GeminiProvider(client, model="m").stream("sys", [UserMessage("hi")], []):
            events.append(event)
    assert events == [TextDelta("Partial")]
