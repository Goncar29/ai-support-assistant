import os
from typing import Optional

MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
SYSTEM_PROMPT = "You are a concise support assistant. Answer in the user's language."


def generate_reply(message: str, client: Optional[object] = None) -> str:
    """Return the LLM reply. Falls back to an echo when no API key is set."""
    if client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return f"[offline mode] You said: {message}"
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model=MODEL,
        max_tokens=512,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": message}],
    )
    return response.content[0].text
