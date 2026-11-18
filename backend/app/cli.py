"""Operational commands: ``python -m app.cli <command>``.

  seed              generate synthetic development data and ingest it (refused in production)
  ingest-dir DIR    ingest every *.json batch in DIR (in file-name order)
  rebuild           recompute every canonical run and character aggregate from raw observations
  rematch           preview (default) or apply re-matching every observation into runs (cluster.py)
  purge-synthetic   delete all synthetic data and everything derived from it
  export-schema     write the observation JSON Schema
  export-openapi    write the OpenAPI document
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

from sqlalchemy import delete, func, select

REPO = Path(__file__).resolve().parents[2]


def _ingest(db, settings, batch: dict, source: str, now: int | None = None):
    from app.ingestion.service import IngestError, ingest_batch

    raw = json.dumps(batch, separators=(",", ":")).encode()
    try:
        result = ingest_batch(
            db, batch, source=source, payload_sha256=hashlib.sha256(raw).hexdigest(), size_bytes=len(raw), settings=settings, now=now
        )
        db.commit()
        return result
    except IngestError as err:
        db.rollback()
        print(f"  batch {batch.get('batch_id')}: {err}", file=sys.stderr)
        return None


def cmd_seed(args) -> int:
    from app.config import get_settings
    from app.db import get_sessionmaker

    settings = get_settings()
    if settings.environment == "production" or not settings.allow_synthetic_data:
        print("refusing to seed synthetic data in this environment", file=sys.stderr)
        return 2
    try:
        from forevertracker_sim import SimConfig, simulate
    except ImportError:
        print("install the simulator first: pip install -e tools/simulator", file=sys.stderr)
        return 2
    cfg = SimConfig(seed=args.seed, characters=args.characters, runs=args.runs, days=args.days)
    sim = simulate(cfg)
    total = len(sim.batches)
    print(f"simulated {len(sim.truth)} runs, {len(sim.characters)} characters, {total} batches (synthetic)")
    db = get_sessionmaker()()
    started = time.time()
    counts: dict[str, int] = {}
    try:
        for i, (upload_at, batch) in enumerate(sim.batches, 1):
            result = _ingest(db, settings, batch, "seed", now=upload_at)
            if result:
                key = "duplicate_batch" if result.duplicate_batch else result.status
                counts[key] = counts.get(key, 0) + 1
            if i % 250 == 0 or i == total:
                rate = i / max(0.001, time.time() - started)
                print(f"  {i}/{total} batches ({rate:.0f}/s)")
    finally:
        db.close()
    print("batch outcomes:", counts)
    return 0


def cmd_ingest_dir(args) -> int:
    from app.config import get_settings
    from app.db import get_sessionmaker

    settings = get_settings()
    db = get_sessionmaker()()
    try:
        for path in sorted(Path(args.directory).glob("*.json")):
            result = _ingest(db, settings, json.loads(path.read_text(encoding="utf-8")), "cli")
            print(f"{path.name}: {result.status if result else 'error'}")
    finally:
        db.close()
    return 0


def cmd_rebuild(_args) -> int:
    from app.config import get_settings
    from app.db import get_sessionmaker
    from app.services.moderation import rebuild_all

    db = get_sessionmaker()()
    try:
        result = rebuild_all(db, get_settings())
        db.commit()
        print(result)
    finally:
        db.close()
    return 0


def cmd_rematch(args) -> int:
    """Re-match every accepted dungeon_run observation from the evidence, as ingestion now does.

    By default this only prints what would change (moves, merges, new runs, unresolved observations) and
    writes nothing. ``--apply --yes`` applies it: run it on a disposable copy first; production also
    needs ``--production``. Raw observations are never changed; a run that loses every observation is
    merged into the run that received them, so its public ID keeps working.
    """
    from collections import Counter

    from sqlalchemy import make_url

    from app.analytics.character_stats import recompute_many
    from app.config import get_settings
    from app.db import get_sessionmaker
    from app.models import AuditLog
    from app.reconciliation import cluster
    from app.reconciliation.consolidate import rebuild_run

    settings = get_settings()
    target = make_url(settings.database_url).render_as_string(hide_password=True)
    db = get_sessionmaker()()
    try:
        _, changes = cluster.plan_all(db, settings)
        report = {
            "database": target,
            "mode": "apply" if args.apply else "dry-run",
            "summary": dict(Counter(c.kind for c in changes)),
            "changes": [{"kind": c.kind, **c.detail} for c in changes],
        }
        print(json.dumps(report, indent=2, default=str))
        if not args.apply:
            db.rollback()
            return 0
        if not args.yes:
            print("refusing to apply without --yes", file=sys.stderr)
            return 2
        if settings.environment == "production" and not args.production:
            print("refusing to apply in production without --production", file=sys.stderr)
            return 2
        touched = cluster.apply_all(db, settings)
        dirty: set[int] = set()
        for run_id in sorted(touched):
            dirty |= rebuild_run(db, run_id, settings)
        recompute_many(db, dirty, settings)
        db.add(AuditLog(actor="cli", action="rematch", target_type="database", target_id="all", details=report["summary"]))
        db.commit()
        print(f"applied: {len(touched)} run(s) rebuilt, {len(dirty)} character(s) recomputed", file=sys.stderr)
        return 0
    finally:
        db.close()


def cmd_purge_synthetic(args) -> int:
    from app.db import get_sessionmaker
    from app.models import (
        Character,
        Contributor,
        Dungeon,
        DungeonRun,
        RawObservation,
        UploadBatch,
    )

    if not args.yes:
        print("this deletes ALL synthetic data; re-run with --yes", file=sys.stderr)
        return 2
    db = get_sessionmaker()()
    try:
        removed = {}
        for model, cond in (
            (DungeonRun, DungeonRun.is_synthetic.is_(True)),
            (RawObservation, RawObservation.is_synthetic.is_(True)),
            (Character, Character.is_synthetic.is_(True)),
            (UploadBatch, UploadBatch.is_synthetic.is_(True)),
            (Contributor, Contributor.is_synthetic.is_(True)),
        ):
            removed[model.__tablename__] = db.execute(delete(model).where(cond)).rowcount
        unused = select(Dungeon.id).where(
            Dungeon.is_synthetic.is_(True), ~select(DungeonRun.id).where(DungeonRun.dungeon_id == Dungeon.id).exists()
        )
        removed["dungeons"] = db.execute(delete(Dungeon).where(Dungeon.id.in_(unused))).rowcount
        db.commit()
        left = db.scalar(select(func.count()).select_from(DungeonRun).where(DungeonRun.is_synthetic.is_(True)))
        print("removed:", removed, "synthetic runs remaining:", left)
    finally:
        db.close()
    return 0


def cmd_export_schema(args) -> int:
    from app.schemas.observations import observation_json_schema

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(observation_json_schema(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    return 0


def cmd_export_openapi(args) -> int:
    from app.main import create_app

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    seed = sub.add_parser("seed", help="generate and ingest synthetic development data")
    seed.add_argument("--characters", type=int, default=2500)
    seed.add_argument("--runs", type=int, default=1200)
    seed.add_argument("--days", type=int, default=35)
    seed.add_argument("--seed", type=int, default=42)
    seed.set_defaults(fn=cmd_seed)
    ing = sub.add_parser("ingest-dir")
    ing.add_argument("directory")
    ing.set_defaults(fn=cmd_ingest_dir)
    sub.add_parser("rebuild").set_defaults(fn=cmd_rebuild)
    rematch = sub.add_parser("rematch", help="preview (default) or apply re-matching observations into runs")
    rematch.add_argument("--apply", action="store_true", help="write the changes (default: only print them)")
    rematch.add_argument("--yes", action="store_true", help="confirm --apply")
    rematch.add_argument("--production", action="store_true", help="allow --apply when ENVIRONMENT=production")
    rematch.set_defaults(fn=cmd_rematch)
    purge = sub.add_parser("purge-synthetic")
    purge.add_argument("--yes", action="store_true")
    purge.set_defaults(fn=cmd_purge_synthetic)
    schema = sub.add_parser("export-schema")
    schema.add_argument("--out", default=str(REPO / "schema" / "observation-batch.v1.schema.json"))
    schema.set_defaults(fn=cmd_export_schema)
    openapi = sub.add_parser("export-openapi")
    openapi.add_argument("--out", default=str(REPO / "docs" / "openapi.json"))
    openapi.set_defaults(fn=cmd_export_openapi)
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
