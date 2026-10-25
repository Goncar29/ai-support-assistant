import json
from typing import Any, Dict, Iterator, List, Sequence

import openai

from app.application.conversation import (
    STOP_END,
    STOP_MAX_TOKENS,
    STOP_REFUSAL,
    STOP_TOOL_USE,
    AssistantMessage,
    LLMEvent,
    Message,
    ModelUnavailable,
    TextDelta,
    ToolCall,
    ToolResultsMessage,
    ToolSpec,
    TurnComplete,
    UserMessage,
)
from app.infrastructure.llm.errors import TRANSIENT_STATUS_CODES

_INCOMPLETE_REASONS = {"max_output_tokens": STOP_MAX_TOKENS, "content_filter": STOP_REFUSAL}
# A turn ends with exactly one of these; each carries the whole response.
_TERMINAL_EVENTS = ("response.completed", "response.incomplete", "response.failed")
# Codes of a failed response that mean the service, not the request, is the problem.
_TRANSIENT_FAILURE_CODES = ("server_error", "rate_limit_exceeded")


class OpenAIProvider:
    """LLMProvider adapter for the OpenAI Responses API (streaming)."""

    # The cap is the cost ceiling of each agent step, the same as the Anthropic adapter's.
    def __init__(self, client: Any, model: str, max_output_tokens: int = 4000):
        self._client = client
        self._model = model
        self._max_output_tokens = max_output_tokens

    def stream(self, system: str, messages: Sequence[Message], tools: Sequence[ToolSpec]) -> Iterator[LLMEvent]:
        try:
            yield from self._stream(system, messages, tools)
        except openai.APIConnectionError as exc:  # includes timeouts
            raise ModelUnavailable(str(exc)) from exc
        except openai.APIStatusError as exc:
            if exc.status_code in TRANSIENT_STATUS_CODES:
                raise ModelUnavailable(str(exc)) from exc
            raise

    def _stream(self, system: str, messages: Sequence[Message], tools: Sequence[ToolSpec]) -> Iterator[LLMEvent]:
        request: Dict[str, Any] = {
            "model": self._model,
            "instructions": system,
            "input": [item for m in messages for item in _to_wire(m)],
            "max_output_tokens": self._max_output_tokens,
            "stream": True,
            # Keep conversations off OpenAI's servers. Reasoning then comes back encrypted,
            # so the next step of the loop can replay it.
            "store": False,
            "include": ["reasoning.encrypted_content"],
        }
        if tools:
            # Strict mode would reject our schemas (it needs additionalProperties: false and has no
            # maxLength); the tools validate their own input instead.
            request["tools"] = [
                {"type": "function", "name": t.name, "description": t.description, "parameters": t.parameters, "strict": False}
                for t in tools
            ]
        # Raw events, not the SDK's stream helper: the helper only accepts response.completed,
        # and a turn cut off by max_output_tokens ends with response.incomplete instead.
        final = None
        with self._client.responses.create(**request) as events:
            for event in events:
                if event.type == "response.output_text.delta":
                    yield TextDelta(event.delta)
                elif event.type in _TERMINAL_EVENTS:
                    final = event.response
        if final is None:
            raise RuntimeError("The OpenAI stream ended before the response finished.")
        if final.status == "failed":
            reason = "OpenAI response failed: %s" % (final.error.message if final.error else "unknown error")
            if final.error and final.error.code in _TRANSIENT_FAILURE_CODES:
                raise ModelUnavailable(reason)
            raise RuntimeError(reason)
        yield TurnComplete(_from_wire(final))


def _from_wire(response: Any) -> AssistantMessage:
    texts: List[str] = []
    calls: List[ToolCall] = []
    refused = False
    for item in response.output:
        if item.type == "message":
            for part in item.content:
                if part.type == "output_text":
                    texts.append(part.text)
                elif part.type == "refusal":
                    refused = True
        elif item.type == "function_call":
            calls.append(ToolCall(item.call_id, item.name, _arguments(item.arguments)))
    return AssistantMessage(
        text="".join(texts),
        tool_calls=tuple(calls),
        stop_reason=_stop_reason(response, refused, calls),
        provider_payload=[item.to_dict() for item in response.output],
    )


def _stop_reason(response: Any, refused: bool, calls: List[ToolCall]) -> str:
    if response.status == "incomplete":
        reason = response.incomplete_details.reason if response.incomplete_details else None
        return _INCOMPLETE_REASONS.get(reason, STOP_END)
    if refused:
        return STOP_REFUSAL
    return STOP_TOOL_USE if calls else STOP_END


def _arguments(raw: str) -> Dict[str, Any]:
    # Unparseable arguments become {}: the tool then fails on missing fields and tells the model.
    try:
        parsed = json.loads(raw)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _to_wire(message: Message) -> List[Dict[str, Any]]:
    if isinstance(message, UserMessage):
        return [{"role": "user", "content": message.text}]
    if isinstance(message, ToolResultsMessage):
        # The "Error: ..." text already tells the model a call failed; this API has no error flag.
        return [{"type": "function_call_output", "call_id": r.call_id, "output": r.content} for r in message.results]
    # Replay our own output items verbatim (reasoning included); rebuild them only for turns from elsewhere.
    if message.provider_payload is not None:
        return list(message.provider_payload)
    items: List[Dict[str, Any]] = [{"role": "assistant", "content": message.text}] if message.text else []
    items += [
        {"type": "function_call", "call_id": c.id, "name": c.name, "arguments": json.dumps(c.arguments)}
        for c in message.tool_calls
    ]
    return items
