from typing import Sequence

from app.application.conversation import AssistantMessage, Message, ToolSpec, UserMessage


class EchoProvider:
    """Offline LLMProvider used when no API key is configured: echoes the user."""

    def complete(self, system: str, messages: Sequence[Message], tools: Sequence[ToolSpec]) -> AssistantMessage:
        last_user = next(m for m in reversed(messages) if isinstance(m, UserMessage))
        return AssistantMessage(text="[offline mode] You said: %s" % last_user.text)
