from fastapi.testclient import TestClient

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
    })
    assert settings == Settings("key", "some-model", "http://n8n.test/hook", ("https://a.com", "https://b.com"))
    assert Settings.from_env({}).cors_origins == ("http://localhost:5173",)


def test_notifier_is_n8n_only_when_url_is_configured():
    assert isinstance(build_notifier(Settings(n8n_webhook_url=None)), NullNotifier)
    assert isinstance(build_notifier(Settings(n8n_webhook_url="http://n8n.test/hook")), N8nNotifier)
