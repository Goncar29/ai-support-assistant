import json
import logging
from typing import Iterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.application.conversation import TextDelta
from app.application.ports import ChatUseCase, RateLimiter, ReplyFinished, ToolStarted
from app.domain.rate_limit import client_key

logger = logging.getLogger(__name__)
router = APIRouter()

STREAM_ERROR_MESSAGE = "Something went wrong. Please try again."
RATE_LIMIT_MESSAGE = "Too many requests. Please try again later."
GLOBAL_RATE_LIMIT_KEY = "chat:global"


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    reply: str


def client_ip(request: Request) -> str:
    if request.app.state.trust_forwarded_for:
        # The proxy overwrites the header; its first entry is the original client.
        forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if forwarded:
            return forwarded
    return request.client.host if request.client else "unknown"


def enforce_rate_limit(request: Request) -> None:
    """Every chat request costs model tokens, so each client gets a budget per time window,
    and all clients together share a global one that caps the total spend.

    The client budget is checked first, so requests it denies never spend the global one.
    """
    _enforce(request.app.state.rate_limiter, "chat:%s" % client_key(client_ip(request)))
    _enforce(request.app.state.global_rate_limiter, GLOBAL_RATE_LIMIT_KEY)


def _enforce(limiter: RateLimiter, key: str) -> None:
    try:
        decision = limiter.hit(key)
    except Exception:  # fail open: a limiter outage must not take the chat down with it
        logger.exception("rate limiter failed; allowing the request")
        return
    if not decision.allowed:
        raise HTTPException(
            status_code=429,
            detail=RATE_LIMIT_MESSAGE,
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/chat", response_model=ChatResponse, dependencies=[Depends(enforce_rate_limit)])
def chat(body: ChatRequest, request: Request) -> ChatResponse:
    chat: ChatUseCase = request.app.state.chat
    return ChatResponse(reply=chat.reply(body.message))


@router.post("/chat/stream", dependencies=[Depends(enforce_rate_limit)])
def chat_stream(body: ChatRequest, request: Request) -> StreamingResponse:
    """Server-Sent Events: `delta` text chunks, `tool` activity, then `done` (or `error`)."""
    chat: ChatUseCase = request.app.state.chat
    return StreamingResponse(
        _sse_events(chat, body.message),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse_events(chat: ChatUseCase, message: str) -> Iterator[str]:
    try:
        for event in chat.run(message):
            if isinstance(event, TextDelta):
                yield _sse("delta", {"text": event.text})
            elif isinstance(event, ToolStarted):
                yield _sse("tool", {"name": event.name})
            elif isinstance(event, ReplyFinished):
                yield _sse("done", {"reply": event.text})
    except Exception:  # headers are already sent, so report in-band without leaking details
        logger.exception("chat stream failed")
        yield _sse("error", {"message": STREAM_ERROR_MESSAGE})


def _sse(event: str, data: dict) -> str:
    return "event: %s\ndata: %s\n\n" % (event, json.dumps(data))
