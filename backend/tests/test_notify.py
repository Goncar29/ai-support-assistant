import json

from app import notify
from app.tools import TICKETS, execute_tool


class FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_no_url_means_no_request(monkeypatch):
    monkeypatch.delenv("N8N_WEBHOOK_URL", raising=False)
    assert notify.notify_ticket_created({"id": "T-1"}) is False


def test_posts_ticket_json(monkeypatch):
    monkeypatch.setenv("N8N_WEBHOOK_URL", "http://n8n.test/webhook/ticket")
    seen = {}

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["body"] = json.loads(request.data)
        return FakeResponse()

    monkeypatch.setattr(notify.urllib.request, "urlopen", fake_urlopen)
    assert notify.notify_ticket_created({"id": "T-1", "title": "x"}) is True
    assert seen["url"] == "http://n8n.test/webhook/ticket"
    assert seen["body"]["id"] == "T-1"


def test_webhook_failure_does_not_break_ticket_creation(monkeypatch):
    monkeypatch.setenv("N8N_WEBHOOK_URL", "http://n8n.test/webhook/ticket")

    def boom(request, timeout):
        raise OSError("connection refused")

    monkeypatch.setattr(notify.urllib.request, "urlopen", boom)
    TICKETS.clear()
    assert execute_tool("create_ticket", {"title": "t", "description": "d"}) == "Ticket T-0001 created."
    assert len(TICKETS) == 1
