import pytest

from app.infrastructure.llm import demo_provider


@pytest.fixture(autouse=True)
def no_demo_word_delay(monkeypatch):
    """The demo paces its replies for the browser; tests run them at full speed."""
    monkeypatch.setattr(demo_provider, "WORD_DELAY_SECONDS", 0)
