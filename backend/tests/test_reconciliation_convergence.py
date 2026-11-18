"""Matching converges on the evidence, whatever order uploads, revisions and retries arrive in.

Each scenario lists the uploads two players' clients make. The outcome (which observations end up in
which run) must not depend on their order, retries must change nothing, and every run ID ever shown must
keep resolving (to the run its observations ended up in).
"""

from __future__ import annotations

import copy

import pytest
from sqlalchemy import select

from app.models import DungeonRun, RawObservation, RunMatchCandidate, RunObservation
from app.services.common import NotFound
from app.services.runs import run_detail
from tests.factories import T0, Member, RunSpec, batch, party, run_observation
from tests.helpers import ingest, runs

A, B = "install-aaaa1111", "install-bbbb2222"


def visible(db) -> list[DungeonRun]:
    return [r for r in runs(db) if r.merged_into_id is None]


def partition(db) -> set[frozenset[str]]:
    """Which accepted observations share a visible run."""
    rows = db.execute(
        select(RunObservation.run_id, RawObservation.observation_key)
        .join(RawObservation, RawObservation.id == RunObservation.raw_observation_id)
        .where(RawObservation.status == "accepted")
    ).all()
    groups: dict[int, set[str]] = {}
    for run_id, key in rows:
        groups.setdefault(run_id, set()).add(key)
    assert set(groups) == {r.id for r in visible(db)}, "every visible run has observations; merged runs have none"
    return {frozenset(g) for g in groups.values()}


def assert_ids_resolve(db, settings, issued: set[str]) -> None:
    """Every run ID ever issued still opens a run page: its own, or the run it was merged into."""
    for public_id in issued:
        try:
            run_detail(db, settings, public_id)
        except NotFound:
            pytest.fail(f"run {public_id} no longer resolves")


def play(db, settings, uploads: dict[str, tuple[str, list[dict]]], order) -> set[str]:
    issued: set[str] = set()
    for key in order:
        installation, observations = uploads[key]
        ingest(db, settings, batch(installation, observations))
        issued |= {r.public_id for r in runs(db)}
    return issued


def with_presence(members: list[Member], presence: dict[str, list[tuple[int, int]]]) -> list[Member]:
    out = copy.deepcopy(members)
    for m in out:
        m.presence = presence.get(m.ref, m.presence)
    return out


# (a) Observer A /reloads 40 s into the run, so a first, in-progress revision is uploaded; B's record of
# the whole run overlaps it by under a minute; A's final revision follows.
EARLY_RELOAD = {
    "A1": (A, [run_observation(RunSpec("a-run", observer="u1", state="in_progress", verified=False, duration=40, encounters=[], combat_seconds=10))]),
    "B": (B, [run_observation(RunSpec("b-run", observer="u3", start=T0 + 20, duration=1780))]),
    "A2": (A, [run_observation(RunSpec("a-run", observer="u1", revision=2))]),
}


@pytest.mark.parametrize("order", [("A1", "B", "A2"), ("B", "A1", "A2"), ("A1", "A2", "B"), ("A2", "B", "A1"), ("B", "A2", "A1")])
def test_an_early_reload_and_a_second_observer_end_in_one_run(db, settings, order):
    issued = play(db, settings, EARLY_RELOAD, order)
    assert partition(db) == {frozenset({"a-run", "b-run"})}
    (run,) = visible(db)
    assert run.match_status == "reconciled" and run.observation_count == 2 and run.contributor_count == 2
    assert_ids_resolve(db, settings, issued)


# (b) The group finished, reset the dungeon and ran it again. An older addon stored A's two runs as one,
# which was uploaded; B uploaded the second run; A's new addon then splits the stored run (the first part
# keeps its ID with a new revision, the second part gets a new ID).
def _reset_scenario():
    both = {m.ref: [(T0, T0 + 3000), (T0 + 3100, T0 + 4000)] for m in party()}
    merged = RunSpec(
        "a-merged", observer="u1", duration=4000, revision=3, state="left", verified=False, combat_seconds=600,
        members=with_presence(party(), both),
        encounters=[(3001, 300, True), (3002, 900, True), (3001, 3400, True), (3002, 3800, True)],
    )
    first = RunSpec("a-merged", observer="u1", duration=3000, revision=4, state="left", verified=False, combat_seconds=400)
    second = RunSpec(
        "a-second", observer="u1", start=T0 + 3100, duration=900, state="left", verified=False, combat_seconds=200,
        encounters=[(3001, 300, True), (3002, 700, True)],
    )
    b = RunSpec(
        "b-second", observer="u3", start=T0 + 3100, duration=900, state="left", verified=False, combat_seconds=200,
        encounters=[(3001, 300, True), (3002, 700, True)],
    )
    return {
        "merged": (A, [run_observation(merged)]),
        "B": (B, [run_observation(b)]),
        "split": (A, [run_observation(first), run_observation(second)]),
    }


RESET = _reset_scenario()


@pytest.mark.parametrize("order", [("merged", "B", "split"), ("merged", "split", "B"), ("B", "merged", "split"), ("split", "B", "merged"), ("B", "split", "merged")])
def test_a_reset_run_split_after_upload_matches_the_second_observer_to_the_second_run(db, settings, order):
    issued = play(db, settings, RESET, order)
    assert partition(db) == {frozenset({"a-merged"}), frozenset({"a-second", "b-second"})}
    assert_ids_resolve(db, settings, issued)


def test_the_first_part_of_a_split_run_keeps_the_merged_runs_id(db, settings):
    ingest(db, settings, batch(*RESET["merged"]))
    (merged_run,) = visible(db)
    for key in ("B", "split"):
        ingest(db, settings, batch(*RESET[key]))
    first = next(r for r in visible(db) if r.observation_count == 1)
    assert first.public_id == merged_run.public_id


# (c) The player left the group outside, joined another group and went back into the same dungeon; an
# older addon recorded both groups as one run. B is in the second group.
G2 = [
    Member("u6", "Kel", "Ashgrove", "Player-4620-0000B6", "DRUID", "NightElf", 18, "TANK"),
    Member("u7", "Ivo", "Marsh", "Player-4620-0000B7", "SHAMAN", "Dwarf", 18, "HEALER"),
    Member("u8", "Lun", "Tarr", "Player-4620-0000B8", "WARLOCK", "Human", 18, "DAMAGER"),
    Member("u9", "Sev", "Orr", "Player-4620-0000B9", "PALADIN", "Human", 18, "DAMAGER"),
]


def _regroup_scenario():
    me, g1 = party()[0], party()[1:]
    merged_members = [copy.deepcopy(me), *copy.deepcopy(g1), *copy.deepcopy(G2)]
    for m in merged_members:
        m.presence = (
            [(T0, T0 + 1800), (T0 + 2000, T0 + 3800)] if m.ref == "u1" else
            [(T0, T0 + 1800)] if m.ref in {"u2", "u3", "u4", "u5"} else [(T0 + 2000, T0 + 3800)]
        )
    merged = RunSpec(
        "a-merged", observer="u1", duration=3800, revision=2, state="left", verified=False, combat_seconds=600,
        members=merged_members, encounters=[(3001, 300, True), (3002, 900, True), (3001, 2300, True), (3002, 2900, True)],
    )
    first = RunSpec("a-merged", observer="u1", members=[me, *g1], revision=3, state="left", verified=False, combat_seconds=300)
    second = RunSpec("a-second", observer="u1", members=[me, *G2], start=T0 + 2000, state="left", verified=False, combat_seconds=300)
    b = RunSpec("b-second", observer="u7", members=[me, *G2], start=T0 + 2010, duration=1790, state="left", verified=False, combat_seconds=300)
    return {
        "merged": (A, [run_observation(merged)]),
        "B": (B, [run_observation(b)]),
        "split": (A, [run_observation(first), run_observation(second)]),
    }


REGROUP = _regroup_scenario()


@pytest.mark.parametrize("order", [("merged", "B", "split"), ("B", "merged", "split"), ("split", "B", "merged")])
def test_a_regrouped_run_split_after_upload_ends_in_two_runs(db, settings, order):
    issued = play(db, settings, REGROUP, order)
    assert partition(db) == {frozenset({"a-merged"}), frozenset({"a-second", "b-second"})}
    assert_ids_resolve(db, settings, issued)


@pytest.mark.parametrize("scenario", [EARLY_RELOAD, RESET, REGROUP], ids=["early-reload", "reset", "regroup"])
def test_retries_in_any_order_change_nothing(db, settings, scenario):
    play(db, settings, scenario, list(scenario))
    before = partition(db)
    visible_ids = {r.public_id for r in visible(db)}
    for key in reversed(list(scenario)):  # every upload again, newest first (stale and duplicate revisions)
        installation, observations = scenario[key]
        ingest(db, settings, {**batch(installation, observations), "batch_id": f"retry-{key}-0001"})
    assert partition(db) == before
    assert {r.public_id for r in visible(db)} == visible_ids


def test_an_ambiguous_observation_stays_reviewable_after_later_uploads(db, settings):
    m = party()
    group_a = [m[0], m[1], Member("u6", "Oro", "Fen", "Player-4620-0000C6", "DRUID", "NightElf", 18, "HEALER")]
    group_b = [m[2], m[3], Member("u7", "Pell", "Fen", "Player-4620-0000C7", "SHAMAN", "Dwarf", 18, "HEALER")]
    ingest(db, settings, batch(A, [run_observation(RunSpec("a-1", observer="u1", members=group_a, encounters=[]))]))
    ingest(db, settings, batch(B, [run_observation(RunSpec("b-1", observer="u3", members=group_b, encounters=[]))]))
    bridge = [m[0], m[1], m[2], m[3]]
    ingest(db, settings, batch("install-cccc3333", [run_observation(RunSpec("c-1", observer="u1", members=bridge, encounters=[]))]))
    # A later, unrelated upload of the same dungeon re-examines the neighbourhood: still unresolved.
    ingest(db, settings, batch("install-dddd4444", [run_observation(RunSpec("d-1", observer="u1", members=group_a, encounters=[], revision=1))]))
    unresolved = [r for r in visible(db) if r.match_status == "unresolved"]
    assert len(unresolved) == 1
    candidates = db.scalars(select(RunMatchCandidate).where(RunMatchCandidate.status == "unresolved")).all()
    assert len(candidates) == 2 and {c.candidate_run_id for c in candidates} <= {r.id for r in visible(db)}
