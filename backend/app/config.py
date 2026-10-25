"""All runtime configuration, read from the environment in one place."""
import os
from dataclasses import dataclass
from typing import Mapping, Optional, Tuple

DEFAULT_MODEL = "claude-haiku-5-5"
DEFAULT_EFFORT = "low"  # chat replies favor latency over deep reasoning
EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")
LLM_PROVIDERS = ("anthropic", "openai", "gemini", "demo")
DEFAULT_OPENAI_MODEL = "gpt-6-luna"  # OpenAI's lowest-cost model with function calling
# gemini-3.8-flash answered 503 "high demand" for hours; Flash-Lite is the fastest and cheapest Flash.
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"
DEFAULT_CORS_ORIGINS = ("http://localhost:5173",)
DEFAULT_RATE_LIMIT_REQUESTS = 10  # chat requests per client...
DEFAULT_RATE_LIMIT_WINDOW_SECONDS = 60  # ...per minute
DEFAULT_GLOBAL_RATE_LIMIT_REQUESTS = 100  # all clients together, per window: caps total model spend


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: Optional[str] = None
    anthropic_model: str = DEFAULT_MODEL
    n8n_webhook_url: Optional[str] = None
    cors_origins: Tuple[str, ...] = DEFAULT_CORS_ORIGINS
    anthropic_effort: str = DEFAULT_EFFORT
    database_url: Optional[str] = None
    rate_limit_requests: int = DEFAULT_RATE_LIMIT_REQUESTS
    rate_limit_window_seconds: int = DEFAULT_RATE_LIMIT_WINDOW_SECONDS
    global_rate_limit_requests: int = DEFAULT_GLOBAL_RATE_LIMIT_REQUESTS
    # Only a proxy that overwrites X-Forwarded-For (Vercel does) makes it safe to read the client IP from it.
    trust_forwarded_for: bool = False
    # Unset keeps the original rule: Claude when ANTHROPIC_API_KEY is set, otherwise demo mode.
    llm_provider: Optional[str] = None
    openai_api_key: Optional[str] = None
    openai_model: str = DEFAULT_OPENAI_MODEL
    gemini_api_key: Optional[str] = None
    gemini_model: str = DEFAULT_GEMINI_MODEL

    @property
    def provider(self) -> str:
        if self.llm_provider:
            return self.llm_provider
        return "anthropic" if self.anthropic_api_key else "demo"

    def __post_init__(self) -> None:
        # Fail at startup, not on the first chat request.
        if self.llm_provider is not None and self.llm_provider not in LLM_PROVIDERS:
            raise ValueError(
                "LLM_PROVIDER must be one of %s, got %r" % (", ".join(LLM_PROVIDERS), self.llm_provider)
            )
        keys = {"anthropic": ("ANTHROPIC_API_KEY", self.anthropic_api_key),
                "openai": ("OPENAI_API_KEY", self.openai_api_key),
                "gemini": ("GEMINI_API_KEY", self.gemini_api_key)}
        if self.provider in keys and not keys[self.provider][1]:
            raise ValueError("LLM_PROVIDER=%s needs %s" % (self.provider, keys[self.provider][0]))
        if self.anthropic_effort not in EFFORT_LEVELS:
            raise ValueError(
                "ANTHROPIC_EFFORT must be one of %s, got %r" % (", ".join(EFFORT_LEVELS), self.anthropic_effort)
            )
        for name, value in (
            ("RATE_LIMIT_REQUESTS", self.rate_limit_requests),
            ("RATE_LIMIT_WINDOW_SECONDS", self.rate_limit_window_seconds),
            ("GLOBAL_RATE_LIMIT_REQUESTS", self.global_rate_limit_requests),
        ):
            if value < 1:
                raise ValueError("%s must be a positive integer, got %r" % (name, value))

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "Settings":
        origins = tuple(o.strip() for o in env.get("CORS_ORIGINS", "").split(",") if o.strip())
        return cls(
            anthropic_api_key=env.get("ANTHROPIC_API_KEY") or None,
            anthropic_model=env.get("ANTHROPIC_MODEL") or DEFAULT_MODEL,
            n8n_webhook_url=env.get("N8N_WEBHOOK_URL") or None,
            cors_origins=origins or DEFAULT_CORS_ORIGINS,
            anthropic_effort=env.get("ANTHROPIC_EFFORT") or DEFAULT_EFFORT,
            database_url=env.get("DATABASE_URL") or None,
            rate_limit_requests=_int(env, "RATE_LIMIT_REQUESTS", DEFAULT_RATE_LIMIT_REQUESTS),
            rate_limit_window_seconds=_int(env, "RATE_LIMIT_WINDOW_SECONDS", DEFAULT_RATE_LIMIT_WINDOW_SECONDS),
            global_rate_limit_requests=_int(env, "GLOBAL_RATE_LIMIT_REQUESTS", DEFAULT_GLOBAL_RATE_LIMIT_REQUESTS),
            trust_forwarded_for=env.get("VERCEL") == "1",  # Vercel sets VERCEL=1 in every deployment
            llm_provider=(env.get("LLM_PROVIDER") or "").strip().lower() or None,
            openai_api_key=env.get("OPENAI_API_KEY") or None,
            openai_model=env.get("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL,
            gemini_api_key=env.get("GEMINI_API_KEY") or None,
            gemini_model=env.get("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL,
        )


def _int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise ValueError("%s must be a positive integer, got %r" % (name, raw)) from None
