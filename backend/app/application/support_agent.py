from typing import Iterator, List, Optional, Sequence

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
from app.application.ports import AgentEvent, LLMProvider, ReplyFinished, ToolStarted
from app.application.support_tools import SupportTools

SYSTEM_PROMPT = (
    "You are a concise support assistant. Answer in the user's language. "
    "Search the FAQ first; create a ticket only if no answer is found."
)
MAX_STEPS = 5
# Earlier turns are resent on every model step, so they are capped like the rest of the cost:
# only the most recent messages that fit in this many characters (about 2000 tokens) are kept.
MAX_HISTORY_CHARS = 8000
GIVE_UP_REPLY = "Sorry, I could not complete that request."
REFUSAL_REPLY = "Sorry, I can't help with that request."


class SupportAgent:
    """Implements the ChatUseCase driving port with a tool-use loop:
    ask the model, run the tools it requests, repeat until it answers."""

    def __init__(self, llm: LLMProvider, tools: SupportTools, max_steps: int = MAX_STEPS):
        self._llm = llm
        self._tools = tools
        self._max_steps = max_steps

    def run(self, message: str, history: Sequence[Message] = ()) -> Iterator[AgentEvent]:
        messages: List[Message] = _conversation(history, message)
        tools = self._tools.start_run()
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
                results.append(tools.execute(call))
            messages.append(ToolResultsMessage(tuple(results)))
        yield ReplyFinished(GIVE_UP_REPLY)

    def reply(self, message: str, history: Sequence[Message] = ()) -> str:
        final = GIVE_UP_REPLY
        for event in self.run(message, history):
            if isinstance(event, ReplyFinished):
                final = event.text
        return final


def _conversation(history: Sequence[Message], message: str) -> List[Message]:
    """The earlier turns that fit in the budget, then the new message, shaped so that every
    provider accepts it: the user speaks first and the roles alternate."""
    recent: List[Message] = []
    used = 0
    for turn in reversed(history):
        if not isinstance(turn, (UserMessage, AssistantMessage)) or not turn.text:
            continue
        used += len(turn.text)
        if used > MAX_HISTORY_CHARS:
            break
        recent.insert(0, turn)
    while recent and not isinstance(recent[0], UserMessage):
        recent.pop(0)
    conversation: List[Message] = []
    for turn in [*recent, UserMessage(message)]:
        previous = conversation[-1] if conversation else None
        if previous is not None and type(previous) is type(turn):
            # A user turn left without a reply (e.g. it failed) joins the next one.
            joined = previous.text + "\n\n" + turn.text
            conversation[-1] = UserMessage(joined) if isinstance(turn, UserMessage) else AssistantMessage(joined)
        else:
            conversation.append(turn if isinstance(turn, UserMessage) else AssistantMessage(turn.text))
    return conversation


def _final_text(turn: AssistantMessage) -> str:
    if turn.text:
        return turn.text
    # Never finish with an empty answer the user would not see.
    return REFUSAL_REPLY if turn.stop_reason == STOP_REFUSAL else GIVE_UP_REPLY
