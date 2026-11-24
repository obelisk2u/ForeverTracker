"""Premade-group completions on the website, from the boss kills the addon uploads.

Groups formed outside the dungeon finder never get a completion event: a run is completed (probable) when it
killed its dungeon's listed final boss (final_encounters.json). The Drowned City cases replay a live full clear
(fixtures/events/forever-drowned-city-full-clear.json) that was stored as 'left' because its final boss was
not listed.
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select

from app.models import DungeonRun
from app.reconciliation import final_encounters as catalog_module
from app.reconciliation import recovery
from app.reconciliation.consolidate import rebuild_run
from app.services.runs import run_detail
from tests.factories import T0, RunSpec, batch, run_observation
from tests.helpers import ingest, runs

REPO = Path(__file__).resolve().parents[2]
TRACE = json.loads((REPO / "fixtures" / "events" / "forever-drowned-city-full-clear.json").read_text(encoding="utf-8"))
MIN_LOTH = 3479


def _drowned_city(obs_id: str, *, observer: str = "u1", state: str = "unknown", start: int = T0, stop_before: int | None = None) -> RunSpec:
    encounters = []
    for e in TRACE["encounters"]:
        if e["encounter_id"] == stop_before:
            break
        encounters.append((e["encounter_id"], e["start"], e["success"]))
    return RunSpec(
        obs_id, observer=observer, map_id=TRACE["instance"]["map_id"], name=TRACE["instance"]["name"], state=state,
        verified=False, start=start, duration=TRACE["duration_seconds"], encounters=encounters,
    )


def _outcome(run: DungeonRun) -> tuple[str, str]:
    return run.outcome, run.completion_confidence


def test_a_premade_full_clear_completes_at_its_final_boss(db, settings):
    # As addon 0.2.12 stores it ('unknown') and as earlier versions did when the player left ('left').
    ingest(db, settings, batch("install-aaaa1111", [run_observation(_drowned_city("r-new"))]))
    ingest(db, settings, batch("install-aaaa1111", [run_observation(_drowned_city("r-old", state="left", start=T0 + 20_000))]))
    for run in runs(db):
        assert _outcome(run) == ("completed", "probable")
        assert run.outcome_evidence == [{"kind": "final_encounter_killed", "encounter_id": MIN_LOTH}]
        detail = run_detail(db, settings, run.public_id)
        assert (detail.outcome, detail.completion_confidence) == ("completed", "probable")


def test_leaving_before_the_final_boss_stays_left(db, settings):
    ingest(db, settings, batch("install-aaaa1111", [run_observation(_drowned_city("r-1", state="left", stop_before=MIN_LOTH))]))
    (run,) = runs(db)
    assert _outcome(run) == ("left", "none")


def test_one_uploader_leaving_early_does_not_undo_anothers_final_kill(db, settings):
    # u3 left before Min'loth; u1 stayed for the kill. Both saw the first five bosses: one run, completed once.
    ingest(db, settings, batch("install-aaaa1111", [run_observation(_drowned_city("a-1", observer="u1"))]))
    ingest(db, settings, batch("install-bbbb2222", [run_observation(_drowned_city("b-1", observer="u3", state="left", stop_before=MIN_LOTH))]))
    (run,) = runs(db)
    assert run.observation_count == 2
    assert _outcome(run) == ("completed", "probable")
    assert run.outcome_evidence == [{"kind": "final_encounter_killed", "encounter_id": MIN_LOTH}]


def test_two_uploaders_of_the_same_final_kill_make_one_completion(db, settings):
    ingest(db, settings, batch("install-aaaa1111", [run_observation(_drowned_city("a-1", observer="u1"))]))
    ingest(db, settings, batch("install-bbbb2222", [run_observation(_drowned_city("b-1", observer="u3", state="left"))]))
    (run,) = runs(db)
    assert _outcome(run) == ("completed", "probable")
    assert len(run.outcome_evidence) == 1


def test_a_dungeon_finder_completion_event_still_outranks_the_kill(db, settings):
    spec = _drowned_city("r-1")
    spec.state, spec.verified = "completed", True
    ingest(db, settings, batch("install-aaaa1111", [run_observation(spec)]))
    (run,) = runs(db)
    assert _outcome(run) == ("completed", "verified")
    assert run.outcome_evidence[0]["kind"] == "lfg_completion_reward"


def test_a_kill_in_a_dungeon_whose_final_boss_is_pending_is_not_guessed(db, settings):
    # Alcaz Prison waits in final_encounters.json "pending" (Blazeroar or The Questioner): its runs stay as recorded.
    spec = RunSpec("r-1", observer="u1", map_id=2994, name="Alcaz Prison", state="left", verified=False, encounters=[(3403, 300, True), (3409, 900, True)])
    ingest(db, settings, batch("install-aaaa1111", [run_observation(spec)]))
    (run,) = runs(db)
    assert _outcome(run) == ("left", "none")
    assert recovery.find(db) == []


def test_runs_stored_before_a_final_boss_was_listed_are_recovered_only_on_request(db, settings, monkeypatch):
    # Stored while The Drowned City had no final boss: the full clear and a run abandoned before Min'loth.
    without = {k: v for k, v in catalog_module.catalog().items() if k != TRACE["instance"]["map_id"]}
    monkeypatch.setattr(catalog_module, "catalog", lambda: without)
    ingest(db, settings, batch("install-aaaa1111", [run_observation(_drowned_city("r-clear", state="left"))]))
    stopped = _drowned_city("r-stop", state="left", start=T0 + 20_000, stop_before=MIN_LOTH)
    ingest(db, settings, batch("install-aaaa1111", [run_observation(stopped)]))
    assert [_outcome(r) for r in runs(db)] == [("left", "none"), ("left", "none")]

    monkeypatch.undo()  # this change lists Min'loth the Serpent
    clear_run, stopped_run = runs(db)

    found = recovery.find(db)
    assert [r.public_id for r in found] == [clear_run.public_id]
    assert found[0].report()["would_be"] == ["completed", "probable"]
    db.expire_all()
    assert [_outcome(r) for r in runs(db)] == [("left", "none"), ("left", "none")], "previewing changes nothing"

    recovery.apply(db, found, settings)
    db.expire_all()
    clear_run, stopped_run = runs(db)
    assert _outcome(clear_run) == ("completed", "probable")
    assert clear_run.outcome_evidence == [{"kind": "final_encounter_killed", "encounter_id": MIN_LOTH}]
    assert _outcome(stopped_run) == ("left", "none"), "a run without the final kill keeps its status"
    assert recovery.find(db) == []

    # The same outcome a full rebuild would derive.
    rebuild_run(db, clear_run.id, settings)
    db.expire_all()
    assert _outcome(db.scalar(select(DungeonRun).where(DungeonRun.id == clear_run.id))) == ("completed", "probable")
