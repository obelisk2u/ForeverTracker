"""Ingestion endpoints. Every payload is untrusted.

The handlers only read the request body on the event loop. Parsing, validation and all database work
(which waits on the ingestion advisory lock) run on a worker thread, with their own session, behind a
per-process gate: at most ``INGEST_CONCURRENCY`` at once and ``INGEST_MAX_WAITING`` queued; past that the
API answers 503 with Retry-After, which the uploader retries. Public reads keep being served meanwhile.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Request
from forevertracker_sv import SavedVariablesError, extract, parse_savedvariables, summarize_export
from forevertracker_sv.parser import ParseLimits
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.deps import client_key, get_db, get_settings, read_limited_body
from app.config import Settings
from app.db import get_sessionmaker
from app.ingestion.service import IngestError, IngestResult, ingest_batch
from app.integrity.ratelimit import upload_limiter
from app.models import UploadBatch
from app.observability import INGEST_BATCHES, INGESTED_OBSERVATIONS
from app.schemas.api import SavedVariablesUploadResult, UploadResult

router = APIRouter(prefix="/api/v1/ingest", tags=["ingestion"])
log = logging.getLogger("forevertracker.ingest")


def _limit(key: str, limit: int) -> None:
    ok, retry = upload_limiter.allow(upload_limiter.hashed(key), limit)
    if not ok:
        raise HTTPException(status_code=429, detail="too many uploads; try again later", headers={"Retry-After": str(retry)})


class IngestGate:
    """At most ``limit`` ingestions at once in this process, and at most ``max_waiting`` queued behind them."""

    def __init__(self, limit: int, max_waiting: int):
        self.loop = asyncio.get_running_loop()
        self.semaphore = asyncio.Semaphore(max(1, limit))
        self.max_waiting = max(0, max_waiting)
        self.waiting = 0
        self.running = 0


def _gate(request: Request, settings: Settings) -> IngestGate:
    gate: IngestGate | None = getattr(request.app.state, "ingest_gate", None)
    if gate is None or gate.loop is not asyncio.get_running_loop():
        gate = IngestGate(settings.ingest_concurrency, settings.ingest_max_waiting)
        request.app.state.ingest_gate = gate
    return gate


async def offload(request: Request, settings: Settings, fn: Callable[..., Any], *args: Any) -> Any:
    """Run ``fn(*args)`` on a worker thread once the gate lets it through."""
    gate = _gate(request, settings)
    if gate.semaphore.locked() and gate.waiting >= gate.max_waiting:
        raise HTTPException(status_code=503, detail="ingestion is busy; try again shortly", headers={"Retry-After": "5"})
    gate.waiting += 1
    try:
        await gate.semaphore.acquire()
    finally:
        gate.waiting -= 1
    gate.running += 1
    try:
        # Not abandoned if the client goes away: the worker finishes (and commits or rolls back) first.
        return await run_in_threadpool(fn, *args)
    finally:
        gate.running -= 1
        gate.semaphore.release()


def _run(db: Session, settings: Settings, payload: dict, source: str, sha: str, size: int) -> IngestResult:
    installation = payload.get("installation_id") if isinstance(payload, dict) else None
    if isinstance(installation, str):
        _limit(f"contrib:{installation}", settings.rate_limit_uploads_per_hour)
    try:
        result = ingest_batch(db, payload, source=source, payload_sha256=sha, size_bytes=size, settings=settings)
        db.commit()
    except IngestError as err:
        db.rollback()
        INGEST_BATCHES.labels(source, err.code).inc()
        raise HTTPException(status_code=err.status_code, detail={"error": err.code, "detail": err.detail}) from None
    except Exception:
        db.rollback()
        raise
    INGEST_BATCHES.labels(source, result.status).inc()
    for obs in result.observations:
        INGESTED_OBSERVATIONS.labels(obs.type or "unknown", obs.status).inc()
    log.info("batch ingested", extra={"upload_id": result.upload_id, "counts": result.counts, "source": source})
    return result


def _ingest_json_batch(settings: Settings, body: bytes, source: str) -> dict:
    """Worker thread: one JSON batch."""
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=422, detail="body is not valid JSON") from None
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="body must be a JSON object")
    db = get_sessionmaker()()
    try:
        return _run(db, settings, payload, source, hashlib.sha256(body).hexdigest(), len(body)).as_dict()
    finally:
        db.close()


def savedvariables_limits(settings: Settings) -> ParseLimits:
    return ParseLimits(max_bytes=settings.max_savedvariables_bytes, max_tokens=settings.max_savedvariables_tokens)


def _ingest_savedvariables(settings: Settings, data: bytes) -> dict:
    """Worker thread: parse a SavedVariables file (bounded by ParseLimits) and ingest its batches."""
    try:
        parsed = parse_savedvariables(data, savedvariables_limits(settings))
    except SavedVariablesError as err:
        raise HTTPException(status_code=422, detail={"error": "invalid_savedvariables", "detail": str(err)}) from None
    return _ingest_export(settings, parsed, data, "savedvariables_upload")


def _ingest_export_string(settings: Settings, data: bytes) -> dict:
    """Worker thread: the JSON string shown by /ft export."""
    try:
        exported = json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=422, detail={"error": "invalid_export", "detail": "not valid JSON"}) from None
    if not isinstance(exported, dict):
        raise HTTPException(status_code=422, detail={"error": "invalid_export", "detail": "expected a JSON object"})
    # JSON keys are strings: the addon's encoder writes Lua list positions as "1", "2"...
    return _ingest_export(settings, {"ForeverTrackerDB": exported}, data, "export_string", string_indices=True)


@router.post("/batches", response_model=UploadResult)
async def upload_batch(request: Request, settings: Settings = Depends(get_settings)):
    """Upload one canonical observation batch (JSON). Used by the desktop uploader."""
    _limit(f"ip:{client_key(request)}", settings.rate_limit_uploads_per_hour_per_ip)
    body = await read_limited_body(request, settings.max_upload_bytes)
    source = "uploader" if request.headers.get("x-forevertracker-client", "").startswith("uploader/") else "api"
    return await offload(request, settings, _ingest_json_batch, settings, body, source)


@router.post("/savedvariables", response_model=SavedVariablesUploadResult)
async def upload_savedvariables(request: Request, settings: Settings = Depends(get_settings)):
    """Upload the ``ForeverTracker.lua`` SavedVariables file (raw body or multipart field ``file``).

    The file is parsed with a data-only parser; nothing in it is executed.
    """
    _limit(f"ip:{client_key(request)}", settings.rate_limit_uploads_per_hour_per_ip)
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("multipart/form-data"):
        form = await request.form(max_files=1, max_fields=2, max_part_size=settings.max_savedvariables_bytes)
        upload = form.get("file")
        if upload is None or isinstance(upload, str):
            raise HTTPException(status_code=422, detail="multipart field 'file' is required")
        data = await upload.read(settings.max_savedvariables_bytes + 1)
        if len(data) > settings.max_savedvariables_bytes:
            raise HTTPException(status_code=413, detail=f"file exceeds {settings.max_savedvariables_bytes} bytes")
    else:
        data = await read_limited_body(request, settings.max_savedvariables_bytes)
    return await offload(request, settings, _ingest_savedvariables, settings, data)


@router.post("/export", response_model=SavedVariablesUploadResult)
async def upload_export_string(request: Request, settings: Settings = Depends(get_settings)):
    """Upload the JSON string shown by the in-game ``/ft export`` command."""
    _limit(f"ip:{client_key(request)}", settings.rate_limit_uploads_per_hour_per_ip)
    data = await read_limited_body(request, settings.max_savedvariables_bytes)
    return await offload(request, settings, _ingest_export_string, settings, data)


def _ingest_export(settings: Settings, parsed: dict, data: bytes, source: str, *, string_indices: bool = False) -> dict:
    try:
        summary = summarize_export(parsed, string_indices=string_indices)
        extraction = extract(
            parsed, max_per_batch=min(200, settings.max_observations_per_batch), string_indices=string_indices
        )
    except SavedVariablesError as err:
        raise HTTPException(status_code=422, detail={"error": "invalid_savedvariables", "detail": str(err)}) from None
    sha = hashlib.sha256(data).hexdigest()
    db = get_sessionmaker()()
    try:
        # Each batch commits on its own, as before: a later batch failing does not undo an earlier one.
        results = [_run(db, settings, b, source, sha, len(data)).as_dict() for b in extraction.batches]
    finally:
        db.close()
    return {
        "batches": results,
        "summary": {
            "dungeon_runs": summary.dungeon_runs,
            "in_progress_runs": summary.in_progress_runs,
            "characters_observed": len(summary.characters_observed),
            "observation_counts": summary.observation_counts,
            "skipped_records": summary.skipped_records,
            # Records left out because a table in them is both a list and a map (see forevertracker_sv.shapes).
            "rejected_records": [r.as_dict() for r in extraction.rejected],
            "synthetic": summary.synthetic,
        },
    }


@router.get("/uploads/{upload_id}")
def get_upload(upload_id: str, db: Session = Depends(get_db)):
    try:
        key = uuid.UUID(upload_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="upload not found") from None
    upload = db.get(UploadBatch, key)
    if upload is None:
        raise HTTPException(status_code=404, detail="upload not found")
    return {
        "upload_id": str(upload.id),
        "status": upload.status,
        "received_at": upload.received_at,
        "processed_at": upload.processed_at,
        "counts": upload.counts,
        "errors": upload.errors,
        "synthetic": upload.is_synthetic,
    }
