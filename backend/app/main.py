"""Composition root: the only place that knows which adapter plugs into which port."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.application.ports import LLMProvider, TicketNotifier
from app.application.support_agent import SupportAgent
from app.application.support_tools import SupportTools
from app.config import Settings
from app.infrastructure.in_memory import DEFAULT_FAQ, InMemoryFaqRepository, InMemoryTicketRepository
from app.infrastructure.llm.echo_provider import EchoProvider
from app.infrastructure.notifications import N8nNotifier, NullNotifier


def build_llm(settings: Settings) -> LLMProvider:
    if not settings.anthropic_api_key:
        return EchoProvider()
    import anthropic

    from app.infrastructure.llm.anthropic_provider import AnthropicProvider

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return AnthropicProvider(client, model=settings.anthropic_model)


def build_notifier(settings: Settings) -> TicketNotifier:
    return N8nNotifier(settings.n8n_webhook_url) if settings.n8n_webhook_url else NullNotifier()


def build_agent(settings: Settings) -> SupportAgent:
    tools = SupportTools(InMemoryFaqRepository(DEFAULT_FAQ), InMemoryTicketRepository(), build_notifier(settings))
    return SupportAgent(build_llm(settings), tools)


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="AI Support Assistant")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.agent = build_agent(settings)
    app.include_router(router)
    return app


app = create_app(Settings.from_env())
