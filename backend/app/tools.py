from typing import Any, Callable, Dict, List

FAQ = {
    "refund": "Refunds are processed within 5 business days after approval.",
    "shipping": "Standard shipping takes 3-7 business days.",
    "password": "Use 'Forgot password' on the login page to reset it.",
}

TICKETS: List[Dict[str, str]] = []

TOOL_SCHEMAS = [
    {
        "name": "search_faq",
        "description": "Search the FAQ for an answer. Use before creating a ticket.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Keywords to search"}},
            "required": ["query"],
        },
    },
    {
        "name": "create_ticket",
        "description": "Create a support ticket when the FAQ has no answer.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "description": {"type": "string"},
            },
            "required": ["title", "description"],
        },
    },
]


def search_faq(query: str) -> str:
    q = query.lower()
    hits = [answer for key, answer in FAQ.items() if key in q]
    return "\n".join(hits) if hits else "No FAQ entry found."


def create_ticket(title: str, description: str) -> str:
    ticket_id = "T-%04d" % (len(TICKETS) + 1)
    TICKETS.append({"id": ticket_id, "title": title, "description": description})
    return "Ticket %s created." % ticket_id


TOOL_HANDLERS: Dict[str, Callable[..., str]] = {
    "search_faq": search_faq,
    "create_ticket": create_ticket,
}


def execute_tool(name: str, args: Dict[str, Any]) -> str:
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        return "Error: unknown tool '%s'." % name
    try:
        return handler(**args)
    except TypeError as exc:
        return "Error: invalid arguments (%s)." % exc
