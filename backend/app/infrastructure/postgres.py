"""Postgres adapter for the ticket repository port (Neon in production).

Each call opens a short-lived connection instead of holding a pool: on
serverless every instance may be frozen or discarded at any time, and Neon's
pooler (PgBouncer) already multiplexes connections on the server side.
"""
from typing import List

import psycopg
from psycopg import sql

from app.domain.ticket import Ticket

CONNECT_TIMEOUT_SECONDS = 10  # Neon may need a few seconds to wake a suspended compute.


def format_ticket_id(number: int) -> str:
    return "T-%04d" % number


class PostgresTicketRepository:
    def __init__(self, database_url: str, schema: str = "public"):
        self._database_url = database_url
        self._table = sql.Identifier(schema, "tickets")
        self._schema = sql.Identifier(schema)

    def _connect(self) -> psycopg.Connection:
        # prepare_threshold=None: PgBouncer in transaction mode cannot keep server-side prepared statements.
        return psycopg.connect(self._database_url, prepare_threshold=None, connect_timeout=CONNECT_TIMEOUT_SECONDS)

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
