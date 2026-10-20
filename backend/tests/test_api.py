import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.application.conversation import TextDelta
from app.application.support_agent import ReplyFinished, ToolStarted
from app.config import Settings
from app.main import build_notifier, create_app
from app.infrastructure.notifications import N8nNotifier, NullNotifier


def make_client(**settings):
    return TestClient(create_app(Settings(**settings)))


def test_health():
    assert make_client().get("/health").json() == {"status": "ok"}


def test_chat_offline_echo_without_api_key():
    res = make_client(anthropic_api_key=None).post("/chat", json={"message": "hola"})
    assert res.status_code == 200
    assert "hola" in res.json()["reply"]


def test_chat_rejects_empty_message():
    assert make_client().post("/chat", json={"message": ""}).status_code == 422


def parse_sse(body):
    events = []
    for frame in body.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in frame.splitlines())
        events.append((fields["event"], json.loads(fields["data"])))
    return events


def test_chat_stream_sends_deltas_then_done():
    res = make_client(anthropic_api_key=None).post("/chat/stream", json={"message": "hola"})

    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(res.text)
    assert events[0] == ("delta", {"text": "[offline mode] You said: hola"})
    assert events[-1] == ("done", {"reply": "[offline mode] You said: hola"})


def test_chat_stream_reports_tool_activity():
    app = create_app(Settings())
    app.state.agent = SimpleNamespace(run=lambda message: iter([ToolStarted("search_faq"), ReplyFinished("ok")]))

    events = parse_sse(TestClient(app).post("/chat/stream", json={"message": "x"}).text)

    assert events == [("tool", {"name": "search_faq"}), ("done", {"reply": "ok"})]


def test_chat_stream_turns_failures_into_an_error_event():
    def failing_run(message):
        yield TextDelta("partial")
        raise RuntimeError("secret upstream detail")

    app = create_app(Settings())
    app.state.agent = SimpleNamespace(run=failing_run)

    events = parse_sse(TestClient(app).post("/chat/stream", json={"message": "x"}).text)

    assert events == [("delta", {"text": "partial"}), ("error", {"message": "Something went wrong. Please try again."})]


def test_chat_stream_rejects_empty_message():
    assert make_client().post("/chat/stream", json={"message": ""}).status_code == 422


def test_cors_allows_only_configured_origins():
    client = make_client(cors_origins=("https://app.example.com",))
    preflight = {"Access-Control-Request-Method": "POST"}
    allowed = client.options("/chat", headers={"Origin": "https://app.example.com", **preflight})
    denied = client.options("/chat", headers={"Origin": "https://evil.example.com", **preflight})
    assert allowed.headers.get("access-control-allow-origin") == "https://app.example.com"
    assert "access-control-allow-origin" not in denied.headers


def test_settings_from_env_parses_values():
    settings = Settings.from_env({
        "ANTHROPIC_API_KEY": "key",
        "ANTHROPIC_MODEL": "some-model",
        "N8N_WEBHOOK_URL": "http://n8n.test/hook",
        "CORS_ORIGINS": "https://a.com, https://b.com",
        "ANTHROPIC_EFFORT": "medium",
    })
    assert settings == Settings(
        "key", "some-model", "http://n8n.test/hook", ("https://a.com", "https://b.com"), "medium"
    )
    defaults = Settings.from_env({})
    assert defaults.cors_origins == ("http://localhost:5173",)
    assert defaults.anthropic_model == "claude-haiku-5-5"
    assert defaults.anthropic_effort == "low"


def test_settings_reject_unknown_effort():
    with pytest.raises(ValueError, match="ANTHROPIC_EFFORT"):
        Settings.from_env({"ANTHROPIC_EFFORT": "lowww"})


def test_notifier_is_n8n_only_when_url_is_configured():
    assert isinstance(build_notifier(Settings(n8n_webhook_url=None)), NullNotifier)
    assert isinstance(build_notifier(Settings(n8n_webhook_url="http://n8n.test/hook")), N8nNotifier)
