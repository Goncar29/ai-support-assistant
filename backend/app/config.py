"""All runtime configuration, read from the environment in one place."""
import os
from dataclasses import dataclass
from typing import Mapping, Optional, Tuple

DEFAULT_MODEL = "claude-haiku-5-5"
DEFAULT_EFFORT = "low"  # chat replies favor latency over deep reasoning
EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")
DEFAULT_CORS_ORIGINS = ("http://localhost:5173",)


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: Optional[str] = None
    anthropic_model: str = DEFAULT_MODEL
    n8n_webhook_url: Optional[str] = None
    cors_origins: Tuple[str, ...] = DEFAULT_CORS_ORIGINS
    anthropic_effort: str = DEFAULT_EFFORT

    def __post_init__(self) -> None:
        # Fail at startup, not on the first chat request.
        if self.anthropic_effort not in EFFORT_LEVELS:
            raise ValueError(
                "ANTHROPIC_EFFORT must be one of %s, got %r" % (", ".join(EFFORT_LEVELS), self.anthropic_effort)
            )

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "Settings":
        origins = tuple(o.strip() for o in env.get("CORS_ORIGINS", "").split(",") if o.strip())
        return cls(
            anthropic_api_key=env.get("ANTHROPIC_API_KEY") or None,
            anthropic_model=env.get("ANTHROPIC_MODEL") or DEFAULT_MODEL,
            n8n_webhook_url=env.get("N8N_WEBHOOK_URL") or None,
            cors_origins=origins or DEFAULT_CORS_ORIGINS,
            anthropic_effort=env.get("ANTHROPIC_EFFORT") or DEFAULT_EFFORT,
        )
