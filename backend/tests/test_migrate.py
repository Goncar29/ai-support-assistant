from app import migrate


def test_migrate_fails_without_database_url(monkeypatch, capsys):
    monkeypatch.setattr(migrate, "load_dotenv", lambda: None)  # ignore any local backend/.env
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert migrate.main() == 1
    assert "DATABASE_URL is not set" in capsys.readouterr().err


def test_migrate_creates_the_schema_when_configured(monkeypatch, capsys):
    created = []
    monkeypatch.setattr(migrate, "load_dotenv", lambda: None)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.test/app")
    monkeypatch.setattr(migrate.PostgresTicketRepository, "create_schema", lambda self: created.append(self))

    assert migrate.main() == 0
    assert len(created) == 1
    assert "Schema is up to date." in capsys.readouterr().out
