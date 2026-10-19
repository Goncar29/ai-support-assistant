import json
import logging
import urllib.request
from dataclasses import asdict

from app.domain.ticket import Ticket

logger = logging.getLogger(__name__)
TIMEOUT_SECONDS = 5


class NullNotifier:
    """Used when no notification channel is configured."""

    def ticket_created(self, ticket: Ticket) -> bool:
        return False


class N8nNotifier:
    """POSTs the ticket to an n8n webhook. Never raises: notification is best-effort."""

    def __init__(self, url: str):
        self._url = url

    def ticket_created(self, ticket: Ticket) -> bool:
        request = urllib.request.Request(
            self._url,
            data=json.dumps(asdict(ticket)).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                return 200 <= response.status < 300
        except Exception as exc:  # network errors must not break ticket creation
            logger.warning("n8n webhook failed: %s", exc)
            return False
