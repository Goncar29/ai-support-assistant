"""Scripted LLMProvider used when no API key is configured.

It speaks the same protocol as a real model, requesting tools and then answering,
so the whole agent loop, the tools, streaming and storage run for real at no cost.
Only the "reasoning" is a fixed script.
"""
import re
from typing import Iterator, Optional, Sequence

from app.application.conversation import (
    STOP_TOOL_USE,
    AssistantMessage,
    LLMEvent,
    Message,
    TextDelta,
    ToolCall,
    ToolResult,
    ToolResultsMessage,
    ToolSpec,
    TurnComplete,
    UserMessage,
)
from app.domain.ticket import DESCRIPTION_MAX_LENGTH

DEMO_PREFIX = "[demo mode] "
TITLE_LENGTH = 60
# Tickets are stored, so only an explicit request opens one; otherwise every
# unmatched message would become a ticket.
TICKET_INTENT_WORDS = ("ticket", "human", "agent", "person")  # also match "humano", "agente", "persona"
NO_FAQ_MATCH_REPLY = (
    "I could not find that in the FAQ. In demo mode I can answer questions about "
    "refunds, shipping or passwords. If you need help with something else, ask me to open a ticket."
)
TICKET_CREATED_REPLY = "I opened ticket %s for you. Our team will get back to you soon."
TICKET_FAILED_REPLY = "Sorry, I could not open the ticket right now. Please try again later."
NO_FAQ_ENTRY = "No FAQ entry found."  # what search_faq returns on a miss

_SEARCH_ID, _TICKET_ID = "demo-search", "demo-ticket"
_TICKET_NUMBER = re.compile(r"Ticket (\S+) created\.")


class DemoProvider:
    def stream(self, system: str, messages: Sequence[Message], tools: Sequence[ToolSpec]) -> Iterator[LLMEvent]:
        question = next(m for m in reversed(messages) if isinstance(m, UserMessage)).text
        result = _last_result(messages)

        if result is None:  # first turn: always look in the FAQ first
            yield from _call(ToolCall(_SEARCH_ID, "search_faq", {"query": question}))
        elif result.call_id == _SEARCH_ID:
            if _wants_ticket(question):
                yield from _call(ToolCall(_TICKET_ID, "create_ticket", {
                    "title": question[:TITLE_LENGTH],
                    "description": question[:DESCRIPTION_MAX_LENGTH],
                }))
            elif result.is_error or result.content == NO_FAQ_ENTRY:
                yield from _answer(NO_FAQ_MATCH_REPLY)
            else:
                yield from _answer(result.content)
        else:
            created = None if result.is_error else _TICKET_NUMBER.search(result.content)
            yield from _answer(TICKET_CREATED_REPLY % created.group(1) if created else TICKET_FAILED_REPLY)


def _last_result(messages: Sequence[Message]) -> Optional[ToolResult]:
    last = messages[-1]
    return last.results[-1] if isinstance(last, ToolResultsMessage) and last.results else None


def _wants_ticket(question: str) -> bool:
    text = question.lower()
    return any(word in text for word in TICKET_INTENT_WORDS)


def _call(call: ToolCall) -> Iterator[LLMEvent]:
    yield TurnComplete(AssistantMessage(text="", tool_calls=(call,), stop_reason=STOP_TOOL_USE))


def _answer(text: str) -> Iterator[LLMEvent]:
    reply = DEMO_PREFIX + text
    # Word by word, so the client sees the same streaming as with a real model.
    for chunk in re.findall(r"\S+\s*", reply):
        yield TextDelta(chunk)
    yield TurnComplete(AssistantMessage(text=reply))
