"""Postgres adapters for the ticket repository and rate limiter ports (Neon in production).

Each call opens a short-lived connection instead of holding a pool: on
serverless every instance may be frozen or discarded at any time, and Neon's
pooler (PgBouncer) already multiplexes connections on the server side.
"""
import contextlib
import logging
import random
import time
from typing import Callable, List

import psycopg
from psycopg import sql

from app.domain.rate_limit import RateLimitDecision, current_window, decide
from app.domain.ticket import Ticket

CONNECT_TIMEOUT_SECONDS = 5  # enough to wake a suspended Neon compute; fail fast when the database is down
PRUNE_PROBABILITY = 0.01  # share of rate limit hits that also delete rows from past windows
PRUNE_BATCH_SIZE = 500  # rows one prune may delete, so a large backlog never slows a single request much

logger = logging.getLogger(__name__)


def format_ticket_id(number: int) -> str:
    return "T-%04d" % number


def connect(database_url: str) -> psycopg.Connection:
    # prepare_threshold=None: PgBouncer in transaction mode cannot keep server-side prepared statements.
    return psycopg.connect(database_url, prepare_threshold=None, connect_timeout=CONNECT_TIMEOUT_SECONDS)


class PostgresTicketRepository:
    def __init__(self, database_url: str, schema: str = "public"):
        self._database_url = database_url
        self._table = sql.Identifier(schema, "tickets")
        self._schema = sql.Identifier(schema)

    def _connect(self) -> psycopg.Connection:
        return connect(self._database_url)

    def create_schema(self) -> None:
        """Create the tickets table if it does not exist. Safe to run more than once."""
        with self._connect() as conn:
            conn.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(self._schema))
            conn.execute(
                sql.SQL(
                    "CREATE TABLE IF NOT EXISTS {} ("
                    " id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,"
                    " title TEXT NOT NULL,"
                    " description TEXT NOT NULL,"
                    " created_at TIMESTAMPTZ NOT NULL DEFAULT now())"
                ).format(self._table)
            )

    def create(self, title: str, description: str) -> Ticket:
        with self._connect() as conn:
            row = conn.execute(
                sql.SQL("INSERT INTO {} (title, description) VALUES (%s, %s) RETURNING id").format(self._table),
                (title, description),
            ).fetchone()
        return Ticket(format_ticket_id(row[0]), title, description)

    def list(self) -> List[Ticket]:
        with self._connect() as conn:
            rows = conn.execute(sql.SQL("SELECT id, title, description FROM {} ORDER BY id").format(self._table))
            return [Ticket(format_ticket_id(id_), title, description) for id_, title, description in rows]


class PostgresRateLimiter:
    """Rate limiter shared by every serverless instance: one row per key, updated atomically.

    The upsert either starts a new window at count 1 or increments the current one, in a
    single statement, so concurrent requests can never both read the same count.

    Rows from past windows are dead weight (the next hit resets them anyway), so a
    small share of hits deletes them, a bounded batch at a time, and the table only
    holds recently active keys.
    """

    def __init__(
        self,
        database_url: str,
        limit: int,
        window_seconds: int,
        schema: str = "public",
        clock: Callable[[], float] = time.time,
        prune_probability: float = PRUNE_PROBABILITY,
        prune_batch_size: int = PRUNE_BATCH_SIZE,
        rng: Callable[[], float] = random.random,
    ):
        self._database_url = database_url
        self._limit = limit
        self._window_seconds = window_seconds
        self._clock = clock
        self._prune_probability = prune_probability
        self._prune_batch_size = prune_batch_size
        self._rng = rng
        self._table = sql.Identifier(schema, "rate_limits")
        self._schema = sql.Identifier(schema)

    def create_schema(self) -> None:
        """Create the rate_limits table and its window_start index if missing. Safe to run more than once."""
        with connect(self._database_url) as conn:
            conn.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(self._schema))
            conn.execute(
                sql.SQL(
                    "CREATE TABLE IF NOT EXISTS {} ("
                    " key TEXT PRIMARY KEY,"
                    " window_start BIGINT NOT NULL,"
                    " count INTEGER NOT NULL)"
                ).format(self._table)
            )
            # Lets a prune find old rows without reading the whole table, even when a flood
            # of distinct clients fills it. Added after the table, so existing tables get it too.
            conn.execute(
                sql.SQL("CREATE INDEX IF NOT EXISTS rate_limits_window_start_idx ON {} (window_start)").format(
                    self._table
                )
            )

    def hit(self, key: str) -> RateLimitDecision:
        start, retry_after = current_window(self._clock(), self._window_seconds)
        with connect(self._database_url) as conn:
            row = conn.execute(
                sql.SQL(
                    "INSERT INTO {t} AS r (key, window_start, count) VALUES (%s, %s, 1)"
                    " ON CONFLICT (key) DO UPDATE SET"
                    " count = CASE WHEN r.window_start = EXCLUDED.window_start THEN r.count + 1 ELSE 1 END,"
                    " window_start = EXCLUDED.window_start"
                    " RETURNING count"
                ).format(t=self._table),
                (key, start),
            ).fetchone()
            conn.commit()  # release the row lock before pruning, so a prune never waits on its own hit
            if self._rng() < self._prune_probability:
                self._prune(conn, start)
        return decide(row[0], self._limit, retry_after)

    def _prune(self, conn: psycopg.Connection, current_start: int) -> None:
        """Delete up to one batch of rows older than the previous window.

        Keeping the previous window is a margin for clock skew between instances: an
        instance whose clock is slightly ahead never deletes a row another instance
        still counts. A failure only skips the cleanup, never the decision.
        """
        try:
            # SKIP LOCKED: a row another request is updating right now is left for a later prune.
            conn.execute(
                sql.SQL(
                    "DELETE FROM {t} WHERE key IN"
                    " (SELECT key FROM {t} WHERE window_start < %s LIMIT %s FOR UPDATE SKIP LOCKED)"
                ).format(t=self._table),
                (current_start - self._window_seconds, self._prune_batch_size),
            )
            conn.commit()
        except psycopg.Error:
            logger.exception("rate limit prune failed; old rows stay until the next prune")
            with contextlib.suppress(psycopg.Error):  # the connection itself may be broken
                conn.rollback()
