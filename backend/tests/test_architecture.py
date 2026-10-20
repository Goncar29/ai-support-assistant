"""Dependency rules of the hexagon, checked on the source imports.

The core (domain + application) knows no technology, and the API (driving
adapter) reaches the core only through its ports.
"""
import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parent.parent / "app"

CORE_FORBIDDEN = ("fastapi", "starlette", "anthropic", "psycopg", "dotenv", "os", "app.infrastructure", "app.api", "app.main", "app.config")
API_FORBIDDEN = ("app.infrastructure", "app.application.support_agent", "app.application.support_tools", "anthropic", "psycopg")


def imported_modules(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module


def violations(folder: str, forbidden):
    found = []
    for path in sorted((APP / folder).rglob("*.py")):
        for module in imported_modules(path):
            if any(module == f or module.startswith(f + ".") for f in forbidden):
                found.append("%s imports %s" % (path.relative_to(APP), module))
    return found


@pytest.mark.parametrize("folder", ["domain", "application"])
def test_core_imports_no_technology(folder):
    assert violations(folder, CORE_FORBIDDEN) == []


def test_api_reaches_the_core_only_through_ports():
    assert violations("api", API_FORBIDDEN) == []
