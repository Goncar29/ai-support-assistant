import json

from app.domain.ticket import Ticket
from app.infrastructure import notifications
from app.infrastructure.notifications import N8nNotifier, NullNotifier

TICKET = Ticket("T-0001", "title", "description")


class FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_null_notifier_sends_nothing():
    assert NullNotifier().ticket_created(TICKET) is False


def test_n8n_posts_ticket_json(monkeypatch):
    seen = {}

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["body"] = json.loads(request.data)
        return FakeResponse()

    monkeypatch.setattr(notifications.urllib.request, "urlopen", fake_urlopen)
    assert N8nNotifier("http://n8n.test/webhook/ticket").ticket_created(TICKET) is True
    assert seen["url"] == "http://n8n.test/webhook/ticket"
    assert seen["body"] == {"id": "T-0001", "title": "title", "description": "description"}


def test_n8n_failure_is_swallowed(monkeypatch):
    def boom(request, timeout):
        raise OSError("connection refused")

    monkeypatch.setattr(notifications.urllib.request, "urlopen", boom)
    assert N8nNotifier("http://n8n.test/webhook/ticket").ticket_created(TICKET) is False
