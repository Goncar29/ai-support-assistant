from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.application.support_agent import SupportAgent

router = APIRouter()


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
