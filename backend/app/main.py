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
from app.infrastructure.llm.demo_provider import DemoProvider
from app.infrastructure.notifications import N8nNotifier, NullNotifier


# A stalled provider call must end in an error event, not a silent chat. google-genai has no
# timeout by default and waited forever on an overloaded model; OpenAI's default is 10 minutes.
LLM_TIMEOUT_SECONDS = 30
# Overload and rate-limit errors are often gone a second later. Two retries with a short backoff
# hide most of them; the adapters turn what is left into ModelUnavailable.
LLM_MAX_RETRIES = 2


def build_llm(settings: Settings) -> LLMProvider:
    # Each SDK is imported only when its provider is chosen, so the others never load.
    if settings.provider == "openai":
        import openai

        from app.infrastructure.llm.openai_provider import OpenAIProvider

        client = openai.OpenAI(api_key=settings.openai_api_key, timeout=LLM_TIMEOUT_SECONDS, max_retries=LLM_MAX_RETRIES)
        return OpenAIProvider(client, model=settings.openai_model)
    if settings.provider == "gemini":
        from google import genai

        from app.infrastructure.llm.gemini_provider import GeminiProvider

        # google-genai counts the first call as an attempt and retries 408, 429 and 5xx by default.
        retry = {"attempts": LLM_MAX_RETRIES + 1, "initial_delay": 1.0, "max_delay": 4.0}
        http_options = {"timeout": LLM_TIMEOUT_SECONDS * 1000, "retry_options": retry}  # timeout in milliseconds
        client = genai.Client(api_key=settings.gemini_api_key, http_options=http_options)
        return GeminiProvider(client, model=settings.gemini_model)
    if settings.provider == "anthropic":
        import anthropic

        from app.infrastructure.llm.anthropic_provider import AnthropicProvider

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=LLM_MAX_RETRIES)
        return AnthropicProvider(client, model=settings.anthropic_model, effort=settings.anthropic_effort)
    return DemoProvider()  # free: a scripted model drives the real tools


def build_notifier(settings: Settings) -> TicketNotifier:
    return N8nNotifier(settings.n8n_webhook_url) if settings.n8n_webhook_url else NullNotifier()


def build_ticket_repository(settings: Settings) -> TicketRepository:
    if not settings.database_url:
        return InMemoryTicketRepository()
    from app.infrastructure.postgres import PostgresTicketRepository

    return PostgresTicketRepository(settings.database_url)


def build_rate_limiter(settings: Settings) -> RateLimiter:
    return _build_limiter(settings, settings.rate_limit_requests)


def build_global_rate_limiter(settings: Settings) -> RateLimiter:
    # Same table and window as the per-client limiter; only the limit differs.
    return _build_limiter(settings, settings.global_rate_limit_requests)


def _build_limiter(settings: Settings, limit: int) -> RateLimiter:
    window = settings.rate_limit_window_seconds
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
    app.state.global_rate_limiter = build_global_rate_limiter(settings)
    app.state.trust_forwarded_for = settings.trust_forwarded_for
    app.include_router(router)
    return app


app = create_app(Settings.from_env())
