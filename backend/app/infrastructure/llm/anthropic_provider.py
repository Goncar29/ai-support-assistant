from typing import Any, Dict, List, Sequence

from app.application.conversation import (
    AssistantMessage,
    Message,
    ToolCall,
    ToolResultsMessage,
    ToolSpec,
    UserMessage,
)


class AnthropicProvider:
    """LLMProvider adapter for the Anthropic Messages API."""

    def __init__(self, client: Any, model: str, max_tokens: int = 1024):
        self._client = client
        self._model = model
        self._max_tokens = max_tokens

    def complete(self, system: str, messages: Sequence[Message], tools: Sequence[ToolSpec]) -> AssistantMessage:
        request: Dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "system": system,
            "messages": [_to_wire(m) for m in messages],
        }
        if tools:
            request["tools"] = [
                {"name": t.name, "description": t.description, "input_schema": t.parameters} for t in tools
            ]
        response = self._client.messages.create(**request)
        return AssistantMessage(
            text="".join(b.text for b in response.content if b.type == "text"),
            tool_calls=tuple(
                ToolCall(b.id, b.name, dict(b.input)) for b in response.content if b.type == "tool_use"
            ),
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
