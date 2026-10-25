"""What every LLM adapter treats as a temporary provider failure."""

# Request timeout, rate limit, server errors and Anthropic's 529 "overloaded".
TRANSIENT_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504, 529})
