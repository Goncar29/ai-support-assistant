"""Provider-neutral conversation types.

The agent loop speaks only these types. Each LLM adapter translates them to and
from its provider's wire format, so swapping providers never touches the loop.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple, Union


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
    # Opaque native content the producing adapter needs to replay this turn
    # verbatim (e.g. thinking blocks). Other layers must not inspect it.
    provider_payload: Optional[Any] = field(default=None, compare=False)


@dataclass(frozen=True)
class ToolResultsMessage:
    results: Tuple[ToolResult, ...]


Message = Union[UserMessage, AssistantMessage, ToolResultsMessage]
