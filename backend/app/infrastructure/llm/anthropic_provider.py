from typing import Any, Dict, Iterator, List, Sequence

from app.application.conversation import (
    STOP_END,
    STOP_MAX_TOKENS,
    STOP_REFUSAL,
    STOP_TOOL_USE,
    AssistantMessage,
    LLMEvent,
    Message,
    TextDelta,
    ToolCall,
    ToolResultsMessage,
    ToolSpec,
    TurnComplete,
    UserMessage,
)

_STOP_REASONS = {"tool_use": STOP_TOOL_USE, "max_tokens": STOP_MAX_TOKENS, "refusal": STOP_REFUSAL}


class AnthropicProvider:
    """LLMProvider adapter for the Anthropic Messages API (streaming)."""

    # Thinking counts toward max_tokens, so leave room beyond the visible answer.
    def __init__(self, client: Any, model: str, effort: str = "low", max_tokens: int = 16000):
        self._client = client
        self._model = model
        self._effort = effort
        self._max_tokens = max_tokens

    def stream(self, system: str, messages: Sequence[Message], tools: Sequence[ToolSpec]) -> Iterator[LLMEvent]:
        request: Dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "output_config": {"effort": self._effort},
            "system": system,
            "messages": [_to_wire(m) for m in messages],
        }
        if tools:
            # No eager_input_streaming: tool inputs are a few words, so streaming them buys
            # nothing and would move input validation from the API onto us.
            request["tools"] = [
                {"name": t.name, "description": t.description, "input_schema": t.parameters} for t in tools
            ]
        with self._client.messages.stream(**request) as stream:
            for event in stream:
                if event.type == "text":
                    yield TextDelta(event.text)
            response = stream.get_final_message()
        yield TurnComplete(_from_wire(response))


def _from_wire(response: Any) -> AssistantMessage:
    return AssistantMessage(
        text="".join(b.text for b in response.content if b.type == "text"),
        tool_calls=tuple(ToolCall(b.id, b.name, dict(b.input)) for b in response.content if b.type == "tool_use"),
        stop_reason=_STOP_REASONS.get(response.stop_reason, STOP_END),
        provider_payload=response.content,
    )


def _to_wire(message: Message) -> Dict[str, Any]:
    if isinstance(message, UserMessage):
        return {"role": "user", "content": message.text}
    if isinstance(message, ToolResultsMessage):
        return {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": r.call_id, "content": r.content, "is_error": r.is_error}
            for r in message.results
        ]}
    # Replay our own native content verbatim; rebuild it only for turns from elsewhere.
    content: Any = message.provider_payload
    if content is None:
        content = _assistant_blocks(message)
    return {"role": "assistant", "content": content}


def _assistant_blocks(message: AssistantMessage) -> List[Dict[str, Any]]:
    blocks: List[Dict[str, Any]] = [{"type": "text", "text": message.text}] if message.text else []
    blocks += [
        {"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments} for c in message.tool_calls
    ]
    return blocks
