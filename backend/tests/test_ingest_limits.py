"""Ingestion stays bounded and off the event loop (app/api/ingest.py)."""

from __future__ import annotations

import asyncio
import json
import threading
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import ingest
from app.config import get_settings
from app.db import get_engine
from tests.factories import T0, RunSpec, batch, run_observation


def post_batch(client, payload):
    return client.post("/api/v1/ingest/batches", content=json.dumps(payload), headers={"Content-Type": "application/json"})


def test_savedvariables_parse_limits_are_controlled_errors(client, monkeypatch):
    settings = get_settings()
    flood = ("ForeverTrackerDB = {" + "1," * 5_000 + "}").encode()
    monkeypatch.setattr(settings, "max_savedvariables_tokens", 1_000)
    res = client.post("/api/v1/ingest/savedvariables", content=flood)
    assert res.status_code == 422
    assert res.json()["detail"] == {"error": "invalid_savedvariables", "detail": "too many tokens (limit 1000) (line 1)"}

    monkeypatch.setattr(settings, "max_savedvariables_tokens", None)  # default: bytes / 3
    monkeypatch.setattr(settings, "max_savedvariables_bytes", 6_000)
    small_flood = ("ForeverTrackerDB = {" + "1," * 2_900 + "}").encode()  # under 6,000 bytes, ~5,800 tokens
    res = client.post("/api/v1/ingest/savedvariables", content=small_flood)
    assert res.status_code == 422 and "too many tokens (limit 2000)" in res.json()["detail"]["detail"]
    assert client.post("/api/v1/ingest/savedvariables", content=b"X = 1\n" + b"--[[\n" * 1000).json()["detail"]["detail"] == (
        "unterminated block comment (line 2)"
    )
    assert client.post("/api/v1/ingest/savedvariables", content=b"x" * 6_001).status_code == 413


def test_parsing_and_database_work_run_off_the_event_loop(client, monkeypatch):
    seen = []
    real = ingest.ingest_batch

    def spy(*args, **kwargs):
        try:
            asyncio.get_running_loop()
            seen.append("event loop")
        except RuntimeError:
            seen.append(threading.current_thread().name)
        return real(*args, **kwargs)

    monkeypatch.setattr(ingest, "ingest_batch", spy)
    assert post_batch(client, batch("install-aaaa1111", [run_observation(RunSpec("r-1", observer="u1"))])).status_code == 200
    assert len(seen) == 1 and seen[0] != "event loop"


def test_sessions_are_returned_to_the_pool_after_every_outcome(client):
    pool = get_engine().pool
    ok = batch("install-aaaa1111", [run_observation(RunSpec("r-1", observer="u1"))])
    assert post_batch(client, ok).status_code == 200
    assert post_batch(client, ok).json()["duplicate_batch"] is True  # idempotent, as before
    reused = {**ok, "observations": [run_observation(RunSpec("r-2", observer="u1", start=T0 + 9000))]}
    assert post_batch(client, reused).status_code == 409  # same batch_id, other content: rolled back
    assert post_batch(client, {"format": "forevertracker.batch"}).status_code == 422
    assert pool.checkedout() == 0


def _request(app_state: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(app=SimpleNamespace(state=app_state))


def test_the_gate_bounds_concurrent_work_and_answers_503_when_full():
    settings = SimpleNamespace(ingest_concurrency=1, ingest_max_waiting=1)
    state = SimpleNamespace()
    release = threading.Event()
    started = threading.Event()

    def slow():
        started.set()
        release.wait(5)
        return "done"

    async def scenario():
        req = _request(state)
        first = asyncio.create_task(ingest.offload(req, settings, slow))
        await asyncio.to_thread(started.wait, 5)
        second = asyncio.create_task(ingest.offload(req, settings, lambda: "queued"))
        await asyncio.sleep(0.05)
        gate = state.ingest_gate
        assert (gate.running, gate.waiting) == (1, 1)
        with pytest.raises(HTTPException) as busy:
            await ingest.offload(req, settings, lambda: "never")
        release.set()
        return busy.value, await first, await second, gate

    busy, first, second, gate = asyncio.run(scenario())
    assert busy.status_code == 503 and busy.headers["Retry-After"] == "5"
    assert (first, second) == ("done", "queued")
    assert (gate.running, gate.waiting) == (0, 0)
