"""Integration tests for the Postgres adapter.

They need a real database, so they only run when TEST_DATABASE_URL is set.
Each run works in its own throwaway schema and drops it afterwards, so it
never touches the application's tables.
"""
import os
import uuid

import pytest

from app.domain.ticket import Ticket
from app.infrastructure.postgres import PostgresTicketRepository

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
