"""Integration tests for the Postgres adapter.

They need a real database, so they only run when TEST_DATABASE_URL is set.
Each run works in its own throwaway schema and drops it afterwards, so it
never touches the application's tables.
"""
import os
import uuid

import pytest

from app.domain.ticket import Ticket
from app.infrastructure.postgres import PostgresRateLimiter, PostgresTicketRepository

DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL is not set")


@pytest.fixture
def schema():
    import psycopg
    from psycopg import sql

    name = "test_%s" % uuid.uuid4().hex[:12]
    yield name
    with psycopg.connect(DATABASE_URL, prepare_threshold=None) as conn:
        conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(name)))


def test_tickets_persist_across_repository_instances(schema):
    repo = PostgresTicketRepository(DATABASE_URL, schema=schema)
    repo.create_schema()

    first = repo.create("Login broken", "Cannot sign in since today")
    second = repo.create("Refund", "Order 42")

    assert first == Ticket("T-0001", "Login broken", "Cannot sign in since today")
    assert second.id == "T-0002"
    # A new instance simulates a restart or another serverless instance.
    assert PostgresTicketRepository(DATABASE_URL, schema=schema).list() == [first, second]


def test_create_schema_is_idempotent(schema):
    repo = PostgresTicketRepository(DATABASE_URL, schema=schema)
    repo.create_schema()
    ticket = repo.create("t", "d")
    repo.create_schema()

    assert repo.list() == [ticket]


def test_rate_limit_is_shared_across_limiter_instances(schema):
    clock = lambda: 1000.0
    first = PostgresRateLimiter(DATABASE_URL, limit=2, window_seconds=60, schema=schema, clock=clock)
    first.create_schema()
    # A second instance simulates another serverless instance with its own memory.
    second = PostgresRateLimiter(DATABASE_URL, limit=2, window_seconds=60, schema=schema, clock=clock)

    assert first.hit("ip").allowed
    assert second.hit("ip").allowed
    denied = first.hit("ip")
    assert not denied.allowed
    assert denied.retry_after_seconds == 20
    assert second.hit("other-ip").allowed


def test_rate_limit_resets_in_the_next_window(schema):
    now = [1000.0]
    limiter = PostgresRateLimiter(DATABASE_URL, limit=1, window_seconds=60, schema=schema, clock=lambda: now[0])
    limiter.create_schema()
    assert limiter.hit("ip").allowed
    assert not limiter.hit("ip").allowed
    now[0] = 1020.0
    assert limiter.hit("ip").allowed


def test_concurrent_hits_never_exceed_the_limit(schema):
    from concurrent.futures import ThreadPoolExecutor

    limiter = PostgresRateLimiter(DATABASE_URL, limit=5, window_seconds=60, schema=schema, clock=lambda: 1000.0)
    limiter.create_schema()
    with ThreadPoolExecutor(max_workers=10) as pool:
        decisions = list(pool.map(lambda _: limiter.hit("ip"), range(10)))

    assert sum(d.allowed for d in decisions) == 5


def rate_limit_keys(schema):
    import psycopg
    from psycopg import sql

    with psycopg.connect(DATABASE_URL, prepare_threshold=None) as conn:
        rows = conn.execute(sql.SQL("SELECT key FROM {} ORDER BY key").format(sql.Identifier(schema, "rate_limits")))
        return [key for (key,) in rows]


def test_rate_limit_prunes_rows_from_past_windows(schema):
    now = [1000.0]
    limiter = PostgresRateLimiter(
        DATABASE_URL, limit=1, window_seconds=60, schema=schema, clock=lambda: now[0], rng=lambda: 0.0
    )
    limiter.create_schema()
    limiter.hit("old-ip")
    now[0] = 1100.0  # next window

    assert limiter.hit("new-ip").allowed
    assert rate_limit_keys(schema) == ["new-ip"]
    # The pruned client starts a fresh window, exactly as before pruning existed.
    assert limiter.hit("old-ip").allowed


def test_rate_limit_prunes_only_on_a_fraction_of_hits(schema):
    now = [1000.0]
    limiter = PostgresRateLimiter(
        DATABASE_URL,
        limit=1,
        window_seconds=60,
        schema=schema,
        clock=lambda: now[0],
        prune_probability=0.01,
        rng=lambda: 0.5,
    )
    limiter.create_schema()
    limiter.hit("old-ip")
    now[0] = 1100.0

    limiter.hit("new-ip")

    assert rate_limit_keys(schema) == ["new-ip", "old-ip"]


def test_rate_limit_prune_keeps_the_previous_window_as_a_clock_skew_margin(schema):
    now = [1000.0]
    limiter = PostgresRateLimiter(
        DATABASE_URL, limit=1, window_seconds=60, schema=schema, clock=lambda: now[0], rng=lambda: 0.0
    )
    limiter.create_schema()
    limiter.hit("previous-window-ip")  # window 960
    now[0] = 1030.0  # window 1020: 960 is only one window old

    limiter.hit("new-ip")

    assert rate_limit_keys(schema) == ["new-ip", "previous-window-ip"]


def test_rate_limit_prune_deletes_at_most_one_batch(schema):
    now = [1000.0]
    limiter = PostgresRateLimiter(
        DATABASE_URL,
        limit=1,
        window_seconds=60,
        schema=schema,
        clock=lambda: now[0],
        rng=lambda: 1.0,  # no prune while seeding
        prune_batch_size=2,
    )
    limiter.create_schema()
    for key in ("old-a", "old-b", "old-c"):
        limiter.hit(key)
    now[0] = 1100.0
    pruning = PostgresRateLimiter(
        DATABASE_URL, limit=1, window_seconds=60, schema=schema, clock=lambda: now[0], rng=lambda: 0.0,
        prune_batch_size=2,
    )

    pruning.hit("new-ip")

    keys = rate_limit_keys(schema)
    assert len(keys) == 2 and "new-ip" in keys  # two of the three old rows went, one waits for the next prune


def test_a_failed_prune_keeps_the_decision(schema, caplog):
    import psycopg
    from psycopg import sql

    def drop_table_then_prune():
        # Runs between the committed hit and the prune, so the DELETE hits a missing table.
        with psycopg.connect(DATABASE_URL, prepare_threshold=None) as conn:
            conn.execute(sql.SQL("DROP TABLE {}").format(sql.Identifier(schema, "rate_limits")))
        return 0.0

    PostgresRateLimiter(DATABASE_URL, limit=1, window_seconds=60, schema=schema).create_schema()
    limiter = PostgresRateLimiter(
        DATABASE_URL, limit=0, window_seconds=60, schema=schema, clock=lambda: 1000.0, rng=drop_table_then_prune
    )

    with caplog.at_level("ERROR", logger="app.infrastructure.postgres"):
        denied = limiter.hit("ip")

    assert not denied.allowed
    assert denied.retry_after_seconds == 20
    assert "rate limit prune failed" in caplog.text


def test_rate_limit_schema_indexes_window_start_also_on_an_existing_table(schema):
    import psycopg
    from psycopg import sql

    # The table as the previous migration created it, without the index.
    with psycopg.connect(DATABASE_URL, prepare_threshold=None) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        conn.execute(
            sql.SQL("CREATE TABLE {} (key TEXT PRIMARY KEY, window_start BIGINT NOT NULL, count INTEGER NOT NULL)").format(
                sql.Identifier(schema, "rate_limits")
            )
        )
    limiter = PostgresRateLimiter(DATABASE_URL, limit=1, window_seconds=60, schema=schema, clock=lambda: 1000.0)

    limiter.create_schema()
    limiter.create_schema()  # still idempotent

    with psycopg.connect(DATABASE_URL, prepare_threshold=None) as conn:
        indexdefs = [
            row[0]
            for row in conn.execute(
                "SELECT indexdef FROM pg_indexes WHERE schemaname = %s AND tablename = 'rate_limits'", (schema,)
            )
        ]
    assert any("(window_start)" in d for d in indexdefs), indexdefs
    assert limiter.hit("ip").allowed


def test_a_prune_skips_rows_locked_by_a_concurrent_hit(schema):
    import threading

    import psycopg
    from psycopg import sql

    now = [1000.0]
    seeding = PostgresRateLimiter(DATABASE_URL, limit=1, window_seconds=60, schema=schema, clock=lambda: now[0], rng=lambda: 1.0)
    seeding.create_schema()
    seeding.hit("locked-ip")
    seeding.hit("free-ip")
    now[0] = 1100.0
    pruning = PostgresRateLimiter(DATABASE_URL, limit=1, window_seconds=60, schema=schema, clock=lambda: now[0], rng=lambda: 0.0)

    outcome = {}

    def pruning_hit():
        try:
            outcome["decision"] = pruning.hit("new-ip")
        except Exception as error:  # surfaced below instead of as a lock-wait failure
            outcome["error"] = error

    worker = threading.Thread(target=pruning_hit)
    holder = psycopg.connect(DATABASE_URL, prepare_threshold=None)
    try:
        # Another request is in the middle of updating this stale row.
        holder.execute(
            sql.SQL("SELECT 1 FROM {} WHERE key = 'locked-ip' FOR UPDATE").format(sql.Identifier(schema, "rate_limits"))
        )
        worker.start()
        worker.join(timeout=5)

        assert not worker.is_alive(), "the prune waited on a row another request holds"
    finally:
        holder.rollback()
        holder.close()
        if worker.is_alive():
            worker.join()
    if "error" in outcome:
        raise outcome["error"]
    assert outcome["decision"].allowed
    assert rate_limit_keys(schema) == ["locked-ip", "new-ip"]
