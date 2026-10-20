"""Fixed-window rate limiting: at most N requests per key in each window of W seconds."""
import math
from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int = 0  # meaningful only when the request is denied


def current_window(now: float, window_seconds: int) -> Tuple[int, int]:
    """Return the start of the window containing `now` and the whole seconds until it ends (at least 1)."""
    start = int(now // window_seconds) * window_seconds
    return start, max(1, math.ceil(start + window_seconds - now))


def decide(count: int, limit: int, retry_after_seconds: int) -> RateLimitDecision:
    """`count` includes the current request."""
    if count <= limit:
        return RateLimitDecision(allowed=True)
    return RateLimitDecision(allowed=False, retry_after_seconds=retry_after_seconds)
