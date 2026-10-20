"""Composition root: the only place that knows which adapter plugs into which port."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.application.ports import ChatUseCase, LLMProvider, RateLimiter, TicketNotifier, TicketRepository
from app.application.support_agent import SupportAgent
from app.application.support_tools import SupportTools
from app.config import Settings
from app.infrastructure.in_memory import (
    DEFAULT_FAQ,
    InMemoryFaqRepository,
    InMemoryRateLimiter,
    InMemoryTicketRepository,
)
from app.infrastructure.llm.echo_provider import EchoProvider
from app.infrastructure.notifications import N8nNotifier, NullNotifier


def build_llm(settings: Settings) -> LLMProvider:
    if not settings.anthropic_api_key:
        return EchoProvider()
    import anthropic

    from app.infrastructure.llm.anthropic_provider import AnthropicProvider

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return AnthropicProvider(client, model=settings.anthropic_model, effort=settings.anthropic_effort)


def build_notifier(settings: Settings) -> TicketNotifier:
    return N8nNotifier(settings.n8n_webhook_url) if settings.n8n_webhook_url else NullNotifier()


def build_ticket_repository(settings: Settings) -> TicketRepository:
    if not settings.database_url:
        return InMemoryTicketRepository()
    from app.infrastructure.postgres import PostgresTicketRepository

    return PostgresTicketRepository(settings.database_url)


def build_rate_limiter(settings: Settings) -> RateLimiter:
    limit, window = settings.rate_limit_requests, settings.rate_limit_window_seconds
    if not settings.database_url:
        return InMemoryRateLimiter(limit, window)
    from app.infrastructure.postgres import PostgresRateLimiter

    return PostgresRateLimiter(settings.database_url, limit, window)


def build_chat(settings: Settings) -> ChatUseCase:
    tools = SupportTools(InMemoryFaqRepository(DEFAULT_FAQ), build_ticket_repository(settings), build_notifier(settings))
    return SupportAgent(build_llm(settings), tools)


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="AI Support Assistant")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Retry-After"],  # not CORS-safelisted; the frontend reads it on a 429
    )
    app.state.chat = build_chat(settings)  # the API only sees the ChatUseCase port
    app.state.rate_limiter = build_rate_limiter(settings)
    app.state.trust_forwarded_for = settings.trust_forwarded_for
    app.include_router(router)
    return app


app = create_app(Settings.from_env())
