from typing import List

from app.application.conversation import Message, ToolResultsMessage, UserMessage
from app.application.ports import LLMProvider
from app.application.support_tools import SupportTools

SYSTEM_PROMPT = (
    "You are a concise support assistant. Answer in the user's language. "
    "Search the FAQ first; create a ticket only if no answer is found."
)
MAX_STEPS = 5
GIVE_UP_REPLY = "Sorry, I could not complete that request."


class SupportAgent:
    """Tool-use loop: ask the model, run the tools it requests, repeat until it answers."""

    def __init__(self, llm: LLMProvider, tools: SupportTools, max_steps: int = MAX_STEPS):
        self._llm = llm
        self._tools = tools
        self._max_steps = max_steps

    def reply(self, message: str) -> str:
        messages: List[Message] = [UserMessage(message)]
        for _ in range(self._max_steps):
            turn = self._llm.complete(SYSTEM_PROMPT, messages, self._tools.specs)
            if not turn.tool_calls:
                return turn.text
            messages.append(turn)
            results = tuple(self._tools.execute(call) for call in turn.tool_calls)
            messages.append(ToolResultsMessage(results))
        return GIVE_UP_REPLY
