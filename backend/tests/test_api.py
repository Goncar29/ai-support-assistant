from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_chat_offline_echo(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    res = client.post("/chat", json={"message": "hola"})
    assert res.status_code == 200
    assert "hola" in res.json()["reply"]


def test_chat_rejects_empty_message():
    assert client.post("/chat", json={"message": ""}).status_code == 422
