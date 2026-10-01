import json
import logging
import os
import urllib.request
from typing import Dict

logger = logging.getLogger(__name__)
TIMEOUT_SECONDS = 5


def notify_ticket_created(ticket: Dict[str, str]) -> bool:
    """POST the ticket to the n8n webhook. Never raises: notification is best-effort."""
    url = os.getenv("N8N_WEBHOOK_URL")
    if not url:
        return False
    request = urllib.request.Request(
        url,
        data=json.dumps(ticket).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return 200 <= response.status < 300
    except Exception as exc:  # network errors must not break ticket creation
        logger.warning("n8n webhook failed: %s", exc)
        return False
