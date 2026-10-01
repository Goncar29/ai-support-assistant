import os
from typing import Any, List, Optional

from app.tools import TOOL_SCHEMAS, execute_tool

MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
SYSTEM_PROMPT = (
    "You are a concise support assistant. Answer in the user's language. "
    "Search the FAQ first; create a ticket only if no answer is found."
)
MAX_STEPS = 5


def generate_reply(message: str, client: Optional[Any] = None) -> str:
    """Run the tool-use loop. Falls back to an echo when no API key is set."""
    if client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return "[offline mode] You said: %s" % message
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)

    messages: List[dict] = [{"role": "user", "content": message}]
    for _ in range(MAX_STEPS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=512,
            system=SYSTEM_PROMPT,
            tools=TOOL_SCHEMAS,
            messages=messages,
        )
        if response.stop_reason != "tool_use":
            return "".join(b.text for b in response.content if b.type == "text")

        messages.append({"role": "assistant", "content": response.content})
        results = [
            {
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": execute_tool(block.name, block.input),
            }
            for block in response.content
            if block.type == "tool_use"
        ]
        messages.append({"role": "user", "content": results})

    return "Sorry, I could not complete that request."
