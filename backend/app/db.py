from __future__ import annotations

import sys
from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


def _disable_psycopg_pipeline() -> None:
    """Work around slow pipelined executemany when connecting through Docker Desktop on Windows.

    Measured on the development machine (Windows 11, Docker Desktop, psycopg 3.3.6) through the
    published port localhost:5433: an executemany of 5 UPDATEs took ~50 ms in pipeline mode
    (~3 ms without it) and some mid-sized single statements (~10 KB) also took ~50 ms, while a
    60 KB statement took ~4 ms. That pattern points at Nagle/delayed-ACK behaviour in the port
    proxy. The same benchmark from a Linux container on the compose network measured 0.12 ms
    per round trip, 0.32 ms per 10 KB insert and 0.29 ms per pipelined executemany, so the
    workaround is applied on Windows hosts only (DB_DISABLE_PIPELINE overrides it). For
    realistic timings run the backend inside compose.
    """
    import psycopg

    psycopg.Pipeline.is_supported = classmethod(lambda cls: False)  # type: ignore[method-assign]


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    disable = settings.db_disable_pipeline if settings.db_disable_pipeline is not None else sys.platform == "win32"
    if disable:
        _disable_psycopg_pipeline()
    return create_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        pool_pre_ping=True,
        echo=settings.db_echo,
        future=True,
    )


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)


def get_db() -> Iterator[Session]:
    db = get_sessionmaker()()
    try:
        yield db
    finally:
        db.close()
