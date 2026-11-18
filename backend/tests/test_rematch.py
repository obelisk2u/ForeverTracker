"""`python -m app.cli rematch`: a read-only preview of re-matching, and its apply step (disposable data only)."""

from __future__ import annotations

import json

from sqlalchemy import select

from app.cli import main
from app.models import AuditLog, DungeonRun, RawObservation, RunObservation
from app.reconciliation.consolidate import rebuild_run
from tests.helpers import runs
from tests.test_reconciliation_convergence import EARLY_RELOAD, RESET, assert_ids_resolve, partition, play, visible


def snapshot(db) -> list[tuple]:
    db.expire_all()
    links = db.execute(select(RunObservation.raw_observation_id, RunObservation.run_id).order_by(RunObservation.raw_observation_id)).all()
    run_rows = db.execute(select(DungeonRun.id, DungeonRun.public_id, DungeonRun.merged_into_id, DungeonRun.observation_count).order_by(DungeonRun.id)).all()
    return [tuple(r) for r in links] + [tuple(r) for r in run_rows]


def move(db, settings, key: str, run_id: int) -> None:
    """Put an observation where the old, order-dependent matcher left it."""
    link = db.scalar(
        select(RunObservation).join(RawObservation, RawObservation.id == RunObservation.raw_observation_id).where(
            RawObservation.observation_key == key, RawObservation.status == "accepted"
        )
    )
    previous = link.run_id
    link.run_id = run_id
    db.flush()
    for rid in {previous, run_id}:
        rebuild_run(db, rid, settings)
    db.commit()


def rematch(capsys, *args) -> dict:
    assert main(["rematch", *args]) == 0
    return json.loads(capsys.readouterr().out)


def test_preview_lists_the_repair_of_a_legacy_false_merge_and_writes_nothing(db, settings, capsys):
    play(db, settings, RESET, ("merged", "B", "split"))
    first = next(r for r in visible(db) if r.observation_count == 1)
    for key in ("a-second", "b-second"):  # what the old matcher did: everything in the first run
        move(db, settings, key, first.id)
    assert partition(db) == {frozenset({"a-merged", "a-second", "b-second"})}
    issued = {r.public_id for r in runs(db)}  # the IDs a legacy database would have shown

    before = snapshot(db)
    report = rematch(capsys)
    assert report["mode"] == "dry-run" and "***" in report["database"]
    assert report["summary"] == {"new_run": 1, "move": 2}
    moves = {c["observation"]: c for c in report["changes"] if c["kind"] == "move"}
    assert set(moves) == {"a-second", "b-second"} and {c["from"] for c in moves.values()} == {first.public_id}
    assert snapshot(db) == before  # nothing written

    assert main(["rematch", "--apply"]) == 2  # needs --yes
    capsys.readouterr()
    report = rematch(capsys, "--apply", "--yes")
    db.expire_all()
    assert partition(db) == {frozenset({"a-merged"}), frozenset({"a-second", "b-second"})}
    assert first.public_id in {r.public_id for r in visible(db)}  # the first part kept its ID
    assert_ids_resolve(db, settings, issued)
    assert db.scalar(select(AuditLog).where(AuditLog.action == "rematch")).details == {"new_run": 1, "move": 2}
    assert rematch(capsys)["changes"] == []  # converged


def test_apply_reunites_a_legacy_split_and_the_old_id_redirects(db, settings, capsys):
    issued = play(db, settings, EARLY_RELOAD, ("A1", "A2", "B"))
    (run,) = visible(db)
    legacy = DungeonRun(namespace_id=run.namespace_id, dungeon_id=run.dungeon_id, started_at=run.started_at, last_observed_at=run.last_observed_at, is_synthetic=True)
    db.add(legacy)
    db.flush()
    move(db, settings, "b-run", legacy.id)
    issued |= {legacy.public_id}
    assert len(visible(db)) == 2

    report = rematch(capsys, "--apply", "--yes")
    assert report["summary"] == {"move": 1, "merge": 1}
    db.expire_all()
    assert partition(db) == {frozenset({"a-run", "b-run"})}
    assert db.get(DungeonRun, legacy.id).merged_into_id == run.id
    assert_ids_resolve(db, settings, issued)


def test_production_apply_needs_its_own_flag(db, settings, capsys, monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    assert main(["rematch", "--apply", "--yes"]) == 2
    assert "refusing to apply in production" in capsys.readouterr().err


def test_turning_off_the_party_guid_veto_reunites_stored_runs_after_a_rematch(db, settings, capsys, monkeypatch):
    # FOREVER_LAUNCH_VALIDATION.md test 10: if members' clients report different party GUIDs for one group.
    from tests.factories import RunSpec, batch, run_observation
    from tests.helpers import ingest

    ingest(db, settings, batch("install-aaaa1111", [run_observation(RunSpec("r-1", observer="u1", party_guid="Party-1-AAA"))]))
    ingest(db, settings, batch("install-bbbb2222", [run_observation(RunSpec("r-2", observer="u2", party_guid="Party-1-BBB"))]))
    assert len(visible(db)) == 2
    monkeypatch.setattr(settings, "match_party_guid_veto", False)
    preview = rematch(capsys)
    assert preview["summary"] == {"move": 1, "merge": 1} and len(visible(db)) == 2  # the preview changes nothing
    rematch(capsys, "--apply", "--yes")
    db.expire_all()
    assert partition(db) == {frozenset({"r-1", "r-2"})}
