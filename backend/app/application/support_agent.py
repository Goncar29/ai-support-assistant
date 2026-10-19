from dataclasses import dataclass
from typing import Iterator, List, Optional, Union

from app.application.conversation import (
    STOP_REFUSAL,
    STOP_TOOL_USE,
    AssistantMessage,
    Message,
    TextDelta,
    ToolResultsMessage,
    TurnComplete,
    UserMessage,
)
from app.application.ports import LLMProvider
from app.application.support_tools import SupportTools

SYSTEM_PROMPT = (
    "You are a concise support assistant. Answer in the user's language. "
    "Search the FAQ first; create a ticket only if no answer is found."
)
MAX_STEPS = 5
GIVE_UP_REPLY = "Sorry, I could not complete that request."
REFUSAL_REPLY = "Sorry, I can't help with that request."


@dataclass(frozen=True)
class ToolStarted:
    name: str


@dataclass(frozen=True)
class ReplyFinished:
    """Last event of a run. `text` is the authoritative final answer."""

    text: str


AgentEvent = Union[TextDelta, ToolStarted, ReplyFinished]


class SupportAgent:
    """Tool-use loop: ask the model, run the tools it requests, repeat until it answers."""

    def __init__(self, llm: LLMProvider, tools: SupportTools, max_steps: int = MAX_STEPS):
        self._llm = llm
        self._tools = tools
        self._max_steps = max_steps

    def run(self, message: str) -> Iterator[AgentEvent]:
        messages: List[Message] = [UserMessage(message)]
        for _ in range(self._max_steps):
            turn: Optional[AssistantMessage] = None
            for event in self._llm.stream(SYSTEM_PROMPT, messages, self._tools.specs):
                if isinstance(event, TurnComplete):
                    turn = event.message
                else:
                    yield event
            if turn is None:
                raise RuntimeError("LLMProvider.stream must end with TurnComplete")

            # Only a turn that ended to use tools has complete tool calls to run.
            if turn.stop_reason != STOP_TOOL_USE or not turn.tool_calls:
                yield ReplyFinished(_final_text(turn))
                return
            messages.append(turn)
            results = []
            for call in turn.tool_calls:
                yield ToolStarted(call.name)
                results.append(self._tools.execute(call))
            messages.append(ToolResultsMessage(tuple(results)))
        yield ReplyFinished(GIVE_UP_REPLY)

    def reply(self, message: str) -> str:
        final = GIVE_UP_REPLY
        for event in self.run(message):
            if isinstance(event, ReplyFinished):
                final = event.text
        return final


def _final_text(turn: AssistantMessage) -> str:
    if turn.text:
        return turn.text
    # Never finish with an empty answer the user would not see.
    return REFUSAL_REPLY if turn.stop_reason == STOP_REFUSAL else GIVE_UP_REPLY
