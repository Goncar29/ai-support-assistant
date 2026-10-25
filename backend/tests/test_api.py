import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.application.conversation import ModelUnavailable, TextDelta
from app.application.ports import ReplyFinished, ToolStarted
from app.config import Settings
from app.main import LLM_MAX_RETRIES, LLM_TIMEOUT_SECONDS, build_llm, build_notifier, build_ticket_repository, create_app
from app.infrastructure.in_memory import InMemoryTicketRepository
from app.infrastructure.llm.anthropic_provider import AnthropicProvider
from app.infrastructure.llm.demo_provider import NO_FAQ_MATCH_REPLY_ES, DemoProvider
from app.infrastructure.llm.gemini_provider import GeminiProvider
from app.infrastructure.llm.openai_provider import OpenAIProvider
from app.infrastructure.notifications import N8nNotifier, NullNotifier
from app.infrastructure.postgres import PostgresTicketRepository


def make_client(**settings):
    return TestClient(create_app(Settings(**settings)))


def test_health():
    assert make_client().get("/health").json() == {"status": "ok"}


def test_chat_runs_in_demo_mode_without_api_key():
    res = make_client(anthropic_api_key=None).post("/chat", json={"message": "How do I reset my password?"})
    assert res.status_code == 200
    assert res.json() == {"reply": "[demo mode] Use 'Forgot password' on the login page to reset it."}


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
    reply = "[modo demo] " + NO_FAQ_MATCH_REPLY_ES  # "hola" is answered in Spanish
    assert events[0] == ("tool", {"name": "search_faq"})
    deltas = [data["text"] for name, data in events if name == "delta"]
    assert len(deltas) > 1 and "".join(deltas) == reply
    assert events[-1] == ("done", {"reply": reply})


def test_chat_stream_reports_tool_activity():
    app = create_app(Settings())
    app.state.chat = SimpleNamespace(run=lambda message: iter([ToolStarted("search_faq"), ReplyFinished("ok")]))

    events = parse_sse(TestClient(app).post("/chat/stream", json={"message": "x"}).text)

    assert events == [("tool", {"name": "search_faq"}), ("done", {"reply": "ok"})]


def test_chat_stream_turns_failures_into_an_error_event():
    def failing_run(message):
        yield TextDelta("partial")
        raise RuntimeError("secret upstream detail")

    app = create_app(Settings())
    app.state.chat = SimpleNamespace(run=failing_run)

    events = parse_sse(TestClient(app).post("/chat/stream", json={"message": "x"}).text)

    assert events == [
        ("delta", {"text": "partial"}),
        ("error", {"code": "server_error", "message": "Something went wrong. Please try again."}),
    ]


def failing_chat(error):
    def run(message):
        yield TextDelta("partial")
        raise error

    def reply(message):
        raise error

    return SimpleNamespace(run=run, reply=reply)


def test_chat_stream_tells_the_client_when_the_model_is_busy():
    app = create_app(Settings())
    app.state.chat = failing_chat(ModelUnavailable("503 from upstream"))

    events = parse_sse(TestClient(app).post("/chat/stream", json={"message": "x"}).text)

    assert events[-1] == (
        "error",
        {"code": "model_unavailable", "message": "The assistant is busy right now. Please try again in a moment."},
    )


def test_chat_answers_503_when_the_model_is_busy():
    app = create_app(Settings())
    app.state.chat = failing_chat(ModelUnavailable("503 from upstream"))

    res = TestClient(app).post("/chat", json={"message": "x"})

    assert res.status_code == 503
    assert res.json() == {"detail": "The assistant is busy right now. Please try again in a moment."}


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


def test_settings_read_openai_and_gemini_values():
    settings = Settings.from_env({
        "LLM_PROVIDER": "openai",
        "OPENAI_API_KEY": "sk-test",
        "OPENAI_MODEL": "gpt-test",
        "GEMINI_API_KEY": "g-test",
        "GEMINI_MODEL": "gemini-test",
    })
    assert (settings.llm_provider, settings.openai_api_key, settings.openai_model) == ("openai", "sk-test", "gpt-test")
    assert (settings.gemini_api_key, settings.gemini_model) == ("g-test", "gemini-test")
    defaults = Settings.from_env({})
    assert (defaults.llm_provider, defaults.openai_model, defaults.gemini_model) == (None, "gpt-6-luna", "gemini-3.8-flash")


@pytest.mark.parametrize("env, provider", [
    ({}, "demo"),
    ({"ANTHROPIC_API_KEY": "k"}, "anthropic"),  # unchanged: a Claude key alone still enables Claude
    ({"LLM_PROVIDER": "demo", "ANTHROPIC_API_KEY": "k"}, "demo"),
    ({"LLM_PROVIDER": "openai", "OPENAI_API_KEY": "k"}, "openai"),
    ({"LLM_PROVIDER": "GEMINI", "GEMINI_API_KEY": "k"}, "gemini"),
])
def test_settings_resolve_the_llm_provider(env, provider):
    assert Settings.from_env(env).provider == provider


def test_settings_reject_an_unknown_provider():
    with pytest.raises(ValueError, match="LLM_PROVIDER must be one of anthropic, openai, gemini, demo"):
        Settings.from_env({"LLM_PROVIDER": "mistral"})


@pytest.mark.parametrize("provider, key", [("openai", "OPENAI_API_KEY"), ("gemini", "GEMINI_API_KEY"), ("anthropic", "ANTHROPIC_API_KEY")])
def test_settings_require_the_chosen_providers_key(provider, key):
    with pytest.raises(ValueError, match="LLM_PROVIDER=%s needs %s" % (provider, key)):
        Settings.from_env({"LLM_PROVIDER": provider})


def test_new_provider_clients_give_up_instead_of_hanging():
    # Without a timeout, google-genai waited forever on an overloaded model and the chat sat silent.
    gemini = build_llm(Settings(llm_provider="gemini", gemini_api_key="k"))
    assert gemini._client._api_client._http_options.timeout == LLM_TIMEOUT_SECONDS * 1000  # milliseconds
    openai_llm = build_llm(Settings(llm_provider="openai", openai_api_key="k"))
    assert openai_llm._client.timeout == LLM_TIMEOUT_SECONDS


def test_provider_clients_retry_transient_failures_twice():
    retry = build_llm(Settings(llm_provider="gemini", gemini_api_key="k"))._client._api_client._http_options.retry_options
    assert retry.attempts == LLM_MAX_RETRIES + 1  # google-genai counts the first call
    assert build_llm(Settings(llm_provider="openai", openai_api_key="k"))._client.max_retries == LLM_MAX_RETRIES
    assert build_llm(Settings(anthropic_api_key="k"))._client.max_retries == LLM_MAX_RETRIES


@pytest.mark.parametrize("settings, adapter", [
    (Settings(), DemoProvider),
    (Settings(anthropic_api_key="k"), AnthropicProvider),
    (Settings(llm_provider="openai", openai_api_key="k"), OpenAIProvider),
    (Settings(llm_provider="gemini", gemini_api_key="k"), GeminiProvider),
])
def test_build_llm_plugs_the_configured_adapter(settings, adapter):
    # Building a client opens no connection, so this needs no network and spends nothing.
    assert isinstance(build_llm(settings), adapter)


def test_notifier_is_n8n_only_when_url_is_configured():
    assert isinstance(build_notifier(Settings(n8n_webhook_url=None)), NullNotifier)
    assert isinstance(build_notifier(Settings(n8n_webhook_url="http://n8n.test/hook")), N8nNotifier)


def test_settings_read_database_url():
    assert Settings.from_env({"DATABASE_URL": "postgresql://u:p@db.test/app"}).database_url == "postgresql://u:p@db.test/app"
    assert Settings.from_env({"DATABASE_URL": ""}).database_url is None


def test_tickets_use_postgres_only_when_database_url_is_configured():
    assert isinstance(build_ticket_repository(Settings()), InMemoryTicketRepository)
    # Building the adapter must not open a connection: cold starts stay fast and the app boots without the DB.
    repo = build_ticket_repository(Settings(database_url="postgresql://u:p@unreachable.invalid/app"))
    assert isinstance(repo, PostgresTicketRepository)


class CannedChat:
    """Any ChatUseCase implementation can drive the API, not only SupportAgent."""

    def run(self, message):
        yield TextDelta("canned ")
        yield ReplyFinished("canned reply to " + message)

    def reply(self, message):
        return "canned reply to " + message


def test_api_is_driven_through_the_chat_port():
    app = create_app(Settings())
    app.state.chat = CannedChat()
    client = TestClient(app)

    assert client.post("/chat", json={"message": "hi"}).json() == {"reply": "canned reply to hi"}
    events = parse_sse(client.post("/chat/stream", json={"message": "hi"}).text)
    assert events == [("delta", {"text": "canned "}), ("done", {"reply": "canned reply to hi"})]
