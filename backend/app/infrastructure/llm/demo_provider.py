"""Scripted LLMProvider used when no API key is configured.

It speaks the same protocol as a real model, requesting tools and then answering,
so the whole agent loop, the tools, streaming and storage run for real at no cost.
Only the "reasoning" is a fixed script.
"""
import re
import time
from typing import Callable, Iterator, Optional, Sequence

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
# Pause between streamed words, so the reply arrives like a model streaming tokens
# (and the UI shows its "speaking" state) instead of all at once.
WORD_DELAY_SECONDS = 0.04
DEMO_PREFIX_ES = "[modo demo] "
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
NO_FAQ_MATCH_REPLY_ES = (
    "No encontré eso en las preguntas frecuentes. En modo demo puedo responder sobre "
    "reembolsos, envíos o contraseñas. Si necesitas ayuda con otra cosa, pídeme que abra un ticket."
)
TICKET_CREATED_REPLY_ES = "Abrí el ticket %s. Nuestro equipo te va a responder pronto."
TICKET_FAILED_REPLY_ES = "Perdón, no pude abrir el ticket ahora. Inténtalo de nuevo más tarde."
# A cheap language guess for the fixed replies: Spanish punctuation or letters, or
# common Spanish words that are not English words too.
_SPANISH = re.compile(
    r"[¿¡ñáéíóú]|\b(el|la|los|las|de|del|que|mi|mis|un|una|por|para|con|es|hola|como|quiero|necesito|pedido|ayuda|hablar)\b",
    re.IGNORECASE,
)
NO_FAQ_ENTRY = "No FAQ entry found."  # what search_faq returns on a miss

_SEARCH_ID, _TICKET_ID = "demo-search", "demo-ticket"
_TICKET_NUMBER = re.compile(r"Ticket (\S+) created\.")


class DemoProvider:
    def __init__(self, word_delay: Optional[float] = None, sleep: Callable[[float], None] = time.sleep):
        self._word_delay = word_delay
        self._sleep = sleep

    def stream(self, system: str, messages: Sequence[Message], tools: Sequence[ToolSpec]) -> Iterator[LLMEvent]:
        question = next(m for m in reversed(messages) if isinstance(m, UserMessage)).text
        result = _last_result(messages)
        spanish = bool(_SPANISH.search(question))

        if result is None:  # first turn: always look in the FAQ first
            yield from _call(ToolCall(_SEARCH_ID, "search_faq", {"query": question}))
        elif result.call_id == _SEARCH_ID:
            if _wants_ticket(question):
                yield from _call(ToolCall(_TICKET_ID, "create_ticket", {
                    "title": question[:TITLE_LENGTH],
                    "description": question[:DESCRIPTION_MAX_LENGTH],
                }))
            elif result.is_error or result.content == NO_FAQ_ENTRY:
                yield from self._answer(NO_FAQ_MATCH_REPLY_ES if spanish else NO_FAQ_MATCH_REPLY, spanish)
            else:
                yield from self._answer(result.content, spanish)
        else:
            created = None if result.is_error else _TICKET_NUMBER.search(result.content)
            if created:
                template = TICKET_CREATED_REPLY_ES if spanish else TICKET_CREATED_REPLY
                yield from self._answer(template % created.group(1), spanish)
            else:
                yield from self._answer(TICKET_FAILED_REPLY_ES if spanish else TICKET_FAILED_REPLY, spanish)

    def _answer(self, text: str, spanish: bool = False) -> Iterator[LLMEvent]:
        reply = (DEMO_PREFIX_ES if spanish else DEMO_PREFIX) + text
        # Read at call time, so tests can turn the pause off for the whole app.
        delay = WORD_DELAY_SECONDS if self._word_delay is None else self._word_delay
        # Word by word, so the client sees the same streaming as with a real model.
        for i, chunk in enumerate(re.findall(r"\S+\s*", reply)):
            if i:
                self._sleep(delay)
            yield TextDelta(chunk)
        yield TurnComplete(AssistantMessage(text=reply))


def _last_result(messages: Sequence[Message]) -> Optional[ToolResult]:
    last = messages[-1]
    return last.results[-1] if isinstance(last, ToolResultsMessage) and last.results else None


def _wants_ticket(question: str) -> bool:
    text = question.lower()
    return any(word in text for word in TICKET_INTENT_WORDS)


def _call(call: ToolCall) -> Iterator[LLMEvent]:
    yield TurnComplete(AssistantMessage(text="", tool_calls=(call,), stop_reason=STOP_TOOL_USE))
