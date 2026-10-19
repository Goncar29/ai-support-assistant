from typing import Iterator, Sequence

from app.application.conversation import AssistantMessage, LLMEvent, Message, TextDelta, ToolSpec, TurnComplete, UserMessage


class EchoProvider:
    """Offline LLMProvider used when no API key is configured: echoes the user."""

    def stream(self, system: str, messages: Sequence[Message], tools: Sequence[ToolSpec]) -> Iterator[LLMEvent]:
        last_user = next(m for m in reversed(messages) if isinstance(m, UserMessage))
        text = "[offline mode] You said: %s" % last_user.text
        yield TextDelta(text)
        yield TurnComplete(AssistantMessage(text=text))
