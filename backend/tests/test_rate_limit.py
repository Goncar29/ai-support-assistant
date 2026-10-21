import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.domain.rate_limit import client_key
from app.infrastructure.in_memory import InMemoryRateLimiter
from app.infrastructure.postgres import PostgresRateLimiter
from app.main import build_rate_limiter, create_app


class FakeClock:
    def __init__(self, now: float = 1000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now


# --- In-memory adapter ------------------------------------------------------


def test_in_memory_limiter_allows_up_to_the_limit_then_denies():
    limiter = InMemoryRateLimiter(limit=2, window_seconds=60, clock=FakeClock(1000.0))
    assert limiter.hit("a").allowed
    assert limiter.hit("a").allowed
    denied = limiter.hit("a")
    assert not denied.allowed
    assert denied.retry_after_seconds == 20  # window [960, 1020) ends 20 s from now


def test_in_memory_limiter_resets_in_the_next_window():
    clock = FakeClock(1000.0)
    limiter = InMemoryRateLimiter(limit=1, window_seconds=60, clock=clock)
    assert limiter.hit("a").allowed
    assert not limiter.hit("a").allowed
    clock.now = 1020.0
    assert limiter.hit("a").allowed


def test_in_memory_limiter_counts_each_key_separately():
    limiter = InMemoryRateLimiter(limit=1, window_seconds=60, clock=FakeClock())
    assert limiter.hit("a").allowed
    assert limiter.hit("b").allowed
    assert not limiter.hit("a").allowed


# --- API --------------------------------------------------------------------


def make_client(**settings):
    return TestClient(create_app(Settings(**settings)))


@pytest.mark.parametrize("path", ["/chat", "/chat/stream"])
def test_chat_endpoints_return_429_with_retry_after_over_the_limit(path):
    client = make_client(rate_limit_requests=2)
    assert client.post(path, json={"message": "hi"}).status_code == 200
    assert client.post(path, json={"message": "hi"}).status_code == 200
    res = client.post(path, json={"message": "hi"})
    assert res.status_code == 429
    assert res.json() == {"detail": "Too many requests. Please try again later."}
    assert 1 <= int(res.headers["Retry-After"]) <= 60


def test_chat_and_stream_share_one_budget():
    client = make_client(rate_limit_requests=1)
    assert client.post("/chat", json={"message": "hi"}).status_code == 200
    assert client.post("/chat/stream", json={"message": "hi"}).status_code == 429


def test_invalid_requests_also_consume_the_budget():
    # The limit runs before body validation, so spamming malformed requests is not free.
    client = make_client(rate_limit_requests=2)
    assert client.post("/chat", json={"message": ""}).status_code == 422
    assert client.post("/chat", json={}).status_code == 422
    assert client.post("/chat", json={"message": "hi"}).status_code == 429


def test_health_is_not_rate_limited():
    client = make_client(rate_limit_requests=1)
    assert all(client.get("/health").status_code == 200 for _ in range(3))


def test_429_keeps_cors_headers_so_the_browser_can_read_it():
    client = make_client(rate_limit_requests=1, cors_origins=("https://app.example.com",))
    headers = {"Origin": "https://app.example.com"}
    client.post("/chat", json={"message": "hi"}, headers=headers)
    res = client.post("/chat", json={"message": "hi"}, headers=headers)
    assert res.status_code == 429
    assert res.headers["access-control-allow-origin"] == "https://app.example.com"
    # Retry-After is not CORS-safelisted: without this the browser hides it from the frontend.
    assert "retry-after" in res.headers["access-control-expose-headers"].lower()


def test_forwarded_for_identifies_the_client_only_when_trusted():
    trusted = make_client(rate_limit_requests=1, trust_forwarded_for=True)
    assert trusted.post("/chat", json={"message": "hi"}, headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 200
    assert trusted.post("/chat", json={"message": "hi"}, headers={"X-Forwarded-For": "2.2.2.2, 10.0.0.1"}).status_code == 200
    assert trusted.post("/chat", json={"message": "hi"}, headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 429

    # Untrusted: a client rotating the header must not get a fresh budget.
    untrusted = make_client(rate_limit_requests=1)
    assert untrusted.post("/chat", json={"message": "hi"}, headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 200
    assert untrusted.post("/chat", json={"message": "hi"}, headers={"X-Forwarded-For": "2.2.2.2"}).status_code == 429


@pytest.mark.parametrize(
    "ip, key",
    [
        ("203.0.113.7", "203.0.113.7"),  # IPv4: one key per address
        ("2001:db8:abcd:12:1a2b:3c4d:5e6f:7a8b", "2001:db8:abcd:12::/64"),  # IPv6: one key per /64
        ("2001:DB8:ABCD:0012:0000:0000:0000:0001", "2001:db8:abcd:12::/64"),  # any spelling of it
        ("::ffff:203.0.113.7", "203.0.113.7"),  # IPv4-mapped IPv6 is the IPv4 client
        ("testclient", "testclient"),  # not an IP: used as is
        ("unknown", "unknown"),
    ],
)
def test_client_key_groups_ipv6_by_64_prefix(ip, key):
    assert client_key(ip) == key


def test_ipv6_clients_in_one_64_share_a_budget():
    client = make_client(rate_limit_requests=1, trust_forwarded_for=True)
    same_64 = ["2001:db8:abcd:12::1", "2001:db8:abcd:12:ffff:ffff:ffff:ffff"]
    other_64 = "2001:db8:abcd:13::1"

    assert client.post("/chat", json={"message": "hi"}, headers={"X-Forwarded-For": same_64[0]}).status_code == 200
    # Rotating the interface bits no longer buys a fresh budget.
    assert client.post("/chat", json={"message": "hi"}, headers={"X-Forwarded-For": same_64[1]}).status_code == 429
    assert client.post("/chat", json={"message": "hi"}, headers={"X-Forwarded-For": other_64}).status_code == 200


def test_a_broken_limiter_does_not_take_the_chat_down():
    client = make_client(rate_limit_requests=1)

    class BrokenLimiter:
        def hit(self, key):
            raise ConnectionError("database is down")

    client.app.state.rate_limiter = BrokenLimiter()
    assert client.post("/chat", json={"message": "hi"}).status_code == 200
    assert client.post("/chat", json={"message": "hi"}).status_code == 200


# --- Configuration and wiring ----------------------------------------------


def test_settings_read_rate_limit_values():
    settings = Settings.from_env({"RATE_LIMIT_REQUESTS": "5", "RATE_LIMIT_WINDOW_SECONDS": "30", "VERCEL": "1"})
    assert settings.rate_limit_requests == 5
    assert settings.rate_limit_window_seconds == 30
    assert settings.trust_forwarded_for is True


def test_settings_rate_limit_defaults():
    settings = Settings.from_env({})
    assert settings.rate_limit_requests == 10
    assert settings.rate_limit_window_seconds == 60
    assert settings.trust_forwarded_for is False


@pytest.mark.parametrize(
    "env",
    [{"RATE_LIMIT_REQUESTS": "0"}, {"RATE_LIMIT_REQUESTS": "ten"}, {"RATE_LIMIT_WINDOW_SECONDS": "-1"}],
)
def test_settings_reject_invalid_rate_limit_values(env):
    with pytest.raises(ValueError, match="RATE_LIMIT_"):
        Settings.from_env(env)


def test_rate_limiter_uses_postgres_only_when_database_url_is_configured():
    assert isinstance(build_rate_limiter(Settings()), InMemoryRateLimiter)
    assert isinstance(build_rate_limiter(Settings(database_url="postgresql://u:p@localhost/db")), PostgresRateLimiter)


@pytest.fixture
def recorded_connect_timeouts(monkeypatch):
    import psycopg

    import app.infrastructure.postgres as postgres

    timeouts = []

    def fake_connect(*args, connect_timeout=None, **kwargs):
        timeouts.append(connect_timeout)
        raise psycopg.OperationalError("database unreachable")

    monkeypatch.setattr(postgres.psycopg, "connect", fake_connect)
    return timeouts


def test_a_rate_limit_hit_gives_up_connecting_after_two_seconds(recorded_connect_timeouts):
    import psycopg

    from app.infrastructure.postgres import PostgresTicketRepository

    limiter = PostgresRateLimiter("postgresql://u:p@db/x", limit=1, window_seconds=60)
    with pytest.raises(psycopg.OperationalError):
        limiter.hit("ip")  # the route fails open on this error
    with pytest.raises(psycopg.OperationalError):
        limiter.create_schema()
    with pytest.raises(psycopg.OperationalError):
        PostgresTicketRepository("postgresql://u:p@db/x").list()

    # Every chat request waits on the limiter, so a database outage costs at most 2 s
    # (psycopg's floor); migrations and tickets keep the longer timeout that wakes Neon.
    assert recorded_connect_timeouts == [2, 5, 5]
