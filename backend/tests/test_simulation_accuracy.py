"""Reconciliation accuracy against the simulator's ground truth.

The simulator knows which observations describe the same real run. After ingesting a
synthetic world we check:

* no false merges: a canonical run never mixes observations of different real runs;
* no splits: all accepted observations of one real run land in the same canonical run;
* every multi-observer run is reconciled.

This measures the matcher on simulated imperfections only (late entry, leaving early,
missing party GUIDs, name-only members); it says nothing about real Forever data.
"""

from collections import defaultdict

import pytest
from sqlalchemy import select

from app.models import Character, DungeonRun, RawObservation, RunObservation
from tests.helpers import ingest

pytestmark = pytest.mark.e2e


@pytest.fixture
def world(db, settings):
    from forevertracker_sim import SimConfig, simulate

    sim = simulate(SimConfig(seed=7, characters=500, runs=140))
    for upload_at, batch in sim.batches:
        ingest(db, settings, batch, now=upload_at)
    return sim


def test_matches_ground_truth(db, world):
    truth_of_key: dict[str, str] = {}
    observers_of_truth: dict[str, set[str]] = defaultdict(set)
    for _, batch in world.batches:
        for obs in batch["observations"]:
            if obs["type"] == "dungeon_run":
                start = int(obs["observation_id"].split("-")[1])
                truth = next(t for t in world.truth if t.start <= start <= t.start + 120)
                truth_of_key[obs["observation_id"]] = truth.key
                observers_of_truth[truth.key].add(batch["installation_id"] + obs["recorded_by"]["name"])

    rows = db.execute(
        select(RawObservation.observation_key, RunObservation.run_id)
        .join(RunObservation, RunObservation.raw_observation_id == RawObservation.id)
        .where(RawObservation.status == "accepted", RawObservation.type == "dungeon_run")
    ).all()
    truths_in_run: dict[int, set[str]] = defaultdict(set)
    runs_of_truth: dict[str, set[int]] = defaultdict(set)
    for key, run_id in rows:
        truths_in_run[run_id].add(truth_of_key[key])
        runs_of_truth[truth_of_key[key]].add(run_id)

    false_merges = {r: t for r, t in truths_in_run.items() if len(t) > 1}
    splits = {t: r for t, r in runs_of_truth.items() if len(r) > 1}
    assert not false_merges, false_merges
    assert not splits, splits

    multi = {t for t, obs in observers_of_truth.items() if len(obs) > 1}
    reconciled = {
        t for t, runs in runs_of_truth.items() if db.get(DungeonRun, next(iter(runs))).contributor_count > 1
    }
    assert multi and reconciled == multi

    # Simulator data never produces non-synthetic records.
    assert db.scalars(select(Character).where(Character.is_synthetic.is_(False))).first() is None
    assert db.scalars(select(DungeonRun).where(DungeonRun.is_synthetic.is_(False))).first() is None
