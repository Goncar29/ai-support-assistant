from typing import Any, Dict, Iterator, List, Optional, Sequence

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

_REFUSAL_REASONS = {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII"}
# Older models may return a call without an id. We give it one locally so the agent can
# match its result, and never send that id back to Gemini, which did not issue it.
_LOCAL_ID_PREFIX = "local-call-"


class GeminiProvider:
    """LLMProvider adapter for the Gemini API (google-genai, streaming generate_content)."""

    # The cap is the cost ceiling of each agent step, the same as the Anthropic adapter's.
    def __init__(self, client: Any, model: str, max_output_tokens: int = 4000):
        self._client = client
        self._model = model
        self._max_output_tokens = max_output_tokens

    def stream(self, system: str, messages: Sequence[Message], tools: Sequence[ToolSpec]) -> Iterator[LLMEvent]:
        config: Dict[str, Any] = {
            "system_instruction": system,
            "max_output_tokens": self._max_output_tokens,
            # The agent loop runs the tools itself.
            "automatic_function_calling": {"disable": True},
        }
        if tools:
            config["tools"] = [{"function_declarations": [
                {"name": t.name, "description": t.description, "parameters_json_schema": t.parameters} for t in tools
            ]}]
        parts: List[Any] = []
        finish_reason: Optional[str] = None
        blocked = False
        for chunk in self._client.models.generate_content_stream(
            model=self._model, contents=_to_wire(messages), config=config
        ):
            if not chunk.candidates:
                # A blocked prompt comes back with feedback and no candidates.
                blocked = blocked or bool(chunk.prompt_feedback and chunk.prompt_feedback.block_reason)
                continue
            candidate = chunk.candidates[0]
            if candidate.finish_reason:
                finish_reason = _name(candidate.finish_reason)
            for part in (candidate.content.parts or []) if candidate.content else []:
                parts.append(part)
                if part.text and not part.thought:
                    yield TextDelta(part.text)
        yield TurnComplete(_from_wire(parts, finish_reason, blocked))


def _name(reason: Any) -> str:
    return getattr(reason, "value", reason)


def _from_wire(parts: List[Any], finish_reason: Optional[str], blocked: bool) -> AssistantMessage:
    calls = tuple(
        ToolCall(p.function_call.id or "%s%d" % (_LOCAL_ID_PREFIX, i), p.function_call.name, dict(p.function_call.args or {}))
        for i, p in enumerate(parts) if p.function_call
    )
    if blocked or finish_reason in _REFUSAL_REASONS:
        stop_reason = STOP_REFUSAL
    elif finish_reason == "MAX_TOKENS":
        stop_reason = STOP_MAX_TOKENS
    else:
        stop_reason = STOP_TOOL_USE if calls else STOP_END
    return AssistantMessage(
        text="".join(p.text for p in parts if p.text and not p.thought),
        tool_calls=calls,
        stop_reason=stop_reason,
        # Native parts keep their thought signatures, which Gemini requires back on the next step.
        provider_payload=parts,
    )


def _to_wire(messages: Sequence[Message]) -> List[Dict[str, Any]]:
    names: Dict[str, str] = {}  # a function_response must name its function; the neutral result only has the id
    contents: List[Dict[str, Any]] = []
    for message in messages:
        if isinstance(message, UserMessage):
            contents.append({"role": "user", "parts": [{"text": message.text}]})
        elif isinstance(message, ToolResultsMessage):
            contents.append({"role": "user", "parts": [
                {"function_response": _function_response(r.call_id, names.get(r.call_id, ""), r.content, r.is_error)}
                for r in message.results
            ]})
        else:
            names.update((c.id, c.name) for c in message.tool_calls)
            contents.append({"role": "model", "parts": _model_parts(message)})
    return contents


def _model_parts(message: AssistantMessage) -> List[Any]:
    # Replay our own native parts verbatim; rebuild them only for turns from elsewhere.
    if message.provider_payload is not None:
        return list(message.provider_payload)
    parts: List[Any] = [{"text": message.text}] if message.text else []
    for c in message.tool_calls:
        call: Dict[str, Any] = {"name": c.name, "args": c.arguments}
        if not c.id.startswith(_LOCAL_ID_PREFIX):
            call = {"id": c.id, **call}
        parts.append({"function_call": call})
    return parts


def _function_response(call_id: str, name: str, content: str, is_error: bool) -> Dict[str, Any]:
    response: Dict[str, Any] = {"name": name, "response": {"error" if is_error else "result": content}}
    if not call_id.startswith(_LOCAL_ID_PREFIX):
        response = {"id": call_id, **response}
    return response
