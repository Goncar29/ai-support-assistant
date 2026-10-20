import json
import logging
from typing import Iterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.application.conversation import TextDelta
from app.application.support_agent import ReplyFinished, SupportAgent, ToolStarted

logger = logging.getLogger(__name__)
router = APIRouter()

STREAM_ERROR_MESSAGE = "Something went wrong. Please try again."


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    reply: str


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest, request: Request) -> ChatResponse:
    agent: SupportAgent = request.app.state.agent
    return ChatResponse(reply=agent.reply(body.message))


@router.post("/chat/stream")
def chat_stream(body: ChatRequest, request: Request) -> StreamingResponse:
    """Server-Sent Events: `delta` text chunks, `tool` activity, then `done` (or `error`)."""
    agent: SupportAgent = request.app.state.agent
    return StreamingResponse(
        _sse_events(agent, body.message),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse_events(agent: SupportAgent, message: str) -> Iterator[str]:
    try:
        for event in agent.run(message):
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
