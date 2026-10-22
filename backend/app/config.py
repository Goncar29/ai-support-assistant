"""All runtime configuration, read from the environment in one place."""
import os
from dataclasses import dataclass
from typing import Mapping, Optional, Tuple

DEFAULT_MODEL = "claude-haiku-5-5"
DEFAULT_EFFORT = "low"  # chat replies favor latency over deep reasoning
EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")
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

    def __post_init__(self) -> None:
        # Fail at startup, not on the first chat request.
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
        )


def _int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise ValueError("%s must be a positive integer, got %r" % (name, raw)) from None
