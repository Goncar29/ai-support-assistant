"""All runtime configuration, read from the environment in one place."""
import os
from dataclasses import dataclass
from typing import Mapping, Optional, Tuple

DEFAULT_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_CORS_ORIGINS = ("http://localhost:5173",)


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: Optional[str] = None
    anthropic_model: str = DEFAULT_MODEL
    n8n_webhook_url: Optional[str] = None
    cors_origins: Tuple[str, ...] = DEFAULT_CORS_ORIGINS

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "Settings":
        origins = tuple(o.strip() for o in env.get("CORS_ORIGINS", "").split(",") if o.strip())
        return cls(
            anthropic_api_key=env.get("ANTHROPIC_API_KEY") or None,
            anthropic_model=env.get("ANTHROPIC_MODEL") or DEFAULT_MODEL,
            n8n_webhook_url=env.get("N8N_WEBHOOK_URL") or None,
            cors_origins=origins or DEFAULT_CORS_ORIGINS,
        )
