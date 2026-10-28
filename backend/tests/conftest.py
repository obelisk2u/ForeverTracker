"""Test configuration.

Tests run against a real PostgreSQL database (``forevertracker_test`` by default, created by
``deploy/postgres/init``). Override with ``TEST_DATABASE_URL``.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://forevertracker:forevertracker_dev@localhost:5433/forevertracker_test",
)
os.environ.setdefault("LOG_JSON", "false")

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.config import get_settings
from app.db import get_engine, get_sessionmaker
from app.integrity.ratelimit import upload_limiter
from app.models import Base

BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def migrated_engine():
    get_settings.cache_clear()
    settings = get_settings()
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.attributes["database_url"] = settings.database_url
    command.upgrade(cfg, "head")
    return get_engine()


def _truncate(engine) -> None:
    names = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))


@pytest.fixture
def db(migrated_engine):
    _truncate(migrated_engine)
    upload_limiter.reset()
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def settings():
    return get_settings()


@pytest.fixture
def client(db):
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c
