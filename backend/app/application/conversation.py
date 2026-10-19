"""Provider-neutral conversation types.

The agent loop speaks only these types. Each LLM adapter translates them to and
from its provider's wire format, so swapping providers never touches the loop.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple, Union

# Why a model turn ended, in provider-neutral terms.
STOP_END = "end"  # the model finished its answer
STOP_TOOL_USE = "tool_use"  # the model wants its tool calls executed
STOP_MAX_TOKENS = "max_tokens"  # output was cut off; tool calls may be incomplete
STOP_REFUSAL = "refusal"  # the model declined to answer


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema of the tool input


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    call_id: str
    content: str
    is_error: bool = False


@dataclass(frozen=True)
class UserMessage:
    text: str


@dataclass(frozen=True)
class AssistantMessage:
    text: str
    tool_calls: Tuple[ToolCall, ...] = ()
    stop_reason: str = STOP_END
    # Opaque native content the producing adapter needs to replay this turn
    # verbatim (e.g. thinking blocks). Other layers must not inspect it.
    provider_payload: Optional[Any] = field(default=None, compare=False)


@dataclass(frozen=True)
class ToolResultsMessage:
    results: Tuple[ToolResult, ...]


Message = Union[UserMessage, AssistantMessage, ToolResultsMessage]


@dataclass(frozen=True)
class TextDelta:
    """A chunk of assistant text, emitted as soon as the provider produces it."""

    text: str


@dataclass(frozen=True)
class TurnComplete:
    """Always the last event of a streamed turn, carrying the whole message."""

    message: AssistantMessage


LLMEvent = Union[TextDelta, TurnComplete]
