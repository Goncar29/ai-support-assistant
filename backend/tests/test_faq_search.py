import pytest

from app.infrastructure.in_memory import DEFAULT_FAQ, InMemoryFaqRepository

FAQ = InMemoryFaqRepository(DEFAULT_FAQ)


@pytest.mark.parametrize("query, topic", [
    ("refund", "refund"),  # unchanged: the topic itself still matches
    ("Refunds policy", "refund"),
    ("¿Cuánto tarda el envío?", "envio"),  # unchanged: accents are ignored
    ("money back", "refund"),
    ("reimbursement", "refund"),
    ("delivery time", "shipping"),
    ("can't log in", "password"),
    ("devolución de mi dinero", "reembolso"),
    ("reintegro", "reembolso"),
    ("fecha de entrega", "envio"),
    ("olvidé mi clave", "contrasena"),
    ("no puedo iniciar sesión", "contrasena"),
])
def test_finds_a_topic_by_its_name_or_a_synonym(query, topic):
    assert FAQ.search(query) == [DEFAULT_FAQ[topic]]


@pytest.mark.parametrize("query", [
    # A broken order needs a ticket, not the shipping times.
    "My order arrived broken",
    "Mi pedido llegó roto",
    "hola",
])
def test_unrelated_queries_find_nothing(query):
    assert FAQ.search(query) == []


def test_custom_entries_match_only_their_topics():
    faq = InMemoryFaqRepository({"warranty": "Two years."})
    assert faq.search("warranty claim") == ["Two years."]
    assert faq.search("money back") == []
