"""Run matching as a function of the evidence, not of the order uploads arrive in.

Several addon users in one group each upload their own record of a run, as often as they /reload, log
out or update the addon (which can split a stored record into two). Matching each upload once, against
whatever had arrived before, made the result depend on arrival order. Here every decision is recomputed
from the current accepted observations:

1. **Neighbourhood.** Starting from the observation being applied, collect every accepted observation it
   could match: same namespace and dungeon, a window within ``MATCH_TIME_PADDING_SECONDS``, and a shared
   character or party GUID, transitively; plus every observation already in a run that is involved.
2. **Clustering** (:func:`cluster`, pure). In start-time order, each observation joins the group whose raw
   evidence it matches (see :func:`evaluate`), founds a new group, or, when several groups match about
   equally, founds a group marked *unresolved* that keeps its candidates for review and attracts no one.
3. **Runs** (:func:`assign_runs`, pure). Each group keeps the existing run that holds most of its
   observations, so public IDs stay put; a run that loses every observation is merged into the run that
   received them (its URL redirects there) instead of disappearing. Groups without a run get a new one.

:func:`plan_all` runs the same steps over a whole database for ``python -m app.cli rematch``.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import DungeonRun, RawObservation, RunMatchCandidate, RunObservation
from app.models.base import from_epoch
from app.reconciliation.matcher import member_intervals, observation_window
from app.reconciliation.metrics import intersect_union_seconds
from app.schemas.observations import DungeonRunObservation

MIN_OVERLAP_SECONDS = 60
ENCOUNTER_ALIGN_SECONDS = 120
ENCOUNTER_CONFLICT_SECONDS = 600
AMBIGUITY_RATIO = 1.5

Interval = tuple[datetime, datetime]


@dataclass
class Obs:
    """One accepted dungeon_run observation, reduced to what matching needs."""

    raw_id: int
    contributor_id: int
    namespace_id: int
    dungeon_id: int
    synthetic: bool
    run_id: int | None  # the run it is linked to now (None: being applied)
    preferred_run_id: int | None  # being applied: the run its previous revision was in
    start: datetime
    end: datetime
    party_guid: str | None
    difficulty_id: int | None
    members: dict[int, list[Interval]]
    pulls: list[tuple[int, datetime, bool | None]]
    identities: dict[str, int]
    observation_key: str = ""
    evidence: dict = field(default_factory=dict)  # how it joined its group (filled by cluster)

    @property
    def order(self) -> tuple[datetime, int]:
        return (self.start, self.raw_id)

    @property
    def home_run(self) -> int | None:
        return self.run_id if self.run_id is not None else self.preferred_run_id


def facts(
    raw: RawObservation,
    obs: DungeonRunObservation,
    identities: dict[str, int],
    *,
    namespace_id: int,
    dungeon_id: int,
    run_id: int | None,
    preferred_run_id: int | None = None,
) -> Obs:
    start, end = observation_window(obs)
    members: dict[int, list[Interval]] = defaultdict(list)
    for ref, char_id in identities.items():
        members[int(char_id)].extend(member_intervals(obs, ref))
    return Obs(
        raw_id=raw.id,
        contributor_id=raw.contributor_id,
        namespace_id=namespace_id,
        dungeon_id=dungeon_id,
        synthetic=raw.is_synthetic,
        run_id=run_id,
        preferred_run_id=preferred_run_id,
        start=start,
        end=end,
        party_guid=obs.party_guid,
        difficulty_id=obs.instance.difficulty_id,
        members=dict(members),
        pulls=[(e.encounter_id, from_epoch(e.started_at), e.success) for e in obs.encounters],
        identities={k: int(v) for k, v in identities.items()},
        observation_key=raw.observation_key,
    )


@dataclass
class Evidence:
    score: float = 0.0
    shared_characters: list[int] = field(default_factory=list)
    party_guid_match: bool = False
    aligned_encounters: int = 0
    time_overlap_ratio: float = 0.0
    vetoes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "score": round(self.score, 3),
            "shared_characters": sorted(self.shared_characters),
            "party_guid_match": self.party_guid_match,
            "aligned_encounters": self.aligned_encounters,
            "time_overlap_ratio": round(self.time_overlap_ratio, 3),
            "vetoes": self.vetoes,
        }


@dataclass
class Group:
    obs: list[Obs]
    unresolved: bool = False
    candidates: list[tuple["Group", Evidence]] = field(default_factory=list)

    def intervals(self) -> dict[int, list[Interval]]:
        out: dict[int, list[Interval]] = defaultdict(list)
        for o in self.obs:
            for char_id, ivs in o.members.items():
                out[char_id].extend(ivs)
        return out

    @property
    def start(self) -> datetime:
        return min(o.start for o in self.obs)

    @property
    def end(self) -> datetime:
        return max(o.end for o in self.obs)


def _overlap(a: Interval, b: Interval) -> float:
    return max(0.0, (min(a[1], b[1]) - max(a[0], b[0])).total_seconds())


def evaluate(group: Group, o: Obs, settings: Settings) -> Evidence:
    """How well ``o`` fits ``group``, from the group's raw evidence (never from derived rows).

    Vetoes, any one of which prevents a match: both sides name party GUIDs and the group's single GUID
    differs (unless ``MATCH_PARTY_GUID_VETO`` is off); difficulties differ; the same boss killed more than
    ``ENCOUNTER_CONFLICT_SECONDS`` apart (a boss dies once per instance, so those are two instance copies).
    """
    ev = Evidence()
    guids = {x.party_guid for x in group.obs if x.party_guid}
    if o.party_guid and len(guids) == 1:
        if o.party_guid in guids:
            ev.party_guid_match = True
        elif settings.match_party_guid_veto:
            ev.vetoes.append("party_guid_mismatch")
    difficulties = {x.difficulty_id for x in group.obs if x.difficulty_id is not None}
    if o.difficulty_id is not None and difficulties and o.difficulty_id not in difficulties:
        ev.vetoes.append("difficulty_mismatch")

    theirs = group.intervals()
    for char_id, ivs in o.members.items():
        if char_id in theirs and intersect_union_seconds(ivs, theirs[char_id]) >= MIN_OVERLAP_SECONDS:
            ev.shared_characters.append(char_id)

    pulls = [(eid, t) for x in group.obs for eid, t, _ in x.pulls]
    kills = [(eid, t) for x in group.obs for eid, t, ok in x.pulls if ok]
    for eid, t, ok in o.pulls:
        if any(e == eid and abs((t - t2).total_seconds()) <= ENCOUNTER_ALIGN_SECONDS for e, t2 in pulls):
            ev.aligned_encounters += 1
        if ok and any(e == eid and abs((t - t2).total_seconds()) > ENCOUNTER_CONFLICT_SECONDS for e, t2 in kills):
            if "boss_killed_at_different_times" not in ev.vetoes:
                ev.vetoes.append("boss_killed_at_different_times")

    shortest = min((o.end - o.start).total_seconds(), (group.end - group.start).total_seconds())
    overlap = _overlap((o.start, o.end), (group.start, group.end))
    ev.time_overlap_ratio = overlap / shortest if shortest > 0 else 1.0
    ev.score = 2.0 * len(ev.shared_characters) + (3.0 if ev.party_guid_match else 0.0) + ev.aligned_encounters + ev.time_overlap_ratio
    return ev


def is_match(ev: Evidence, settings: Settings) -> bool:
    if ev.vetoes:
        return False
    if len(ev.shared_characters) >= settings.match_min_shared_characters:
        return True
    return ev.party_guid_match and len(ev.shared_characters) >= 1


def cluster(observations: list[Obs], settings: Settings) -> list[Group]:
    """Partition observations into runs. Deterministic for a given set, whatever order it arrived in."""
    groups: list[Group] = []
    for o in sorted(observations, key=lambda x: x.order):
        evaluated = [(g, evaluate(g, o, settings)) for g in groups if not g.unresolved]
        matches = sorted(((g, ev) for g, ev in evaluated if is_match(ev, settings)), key=lambda m: -m[1].score)
        if not matches:
            o.evidence = {"created_run": True}
            groups.append(Group([o]))
        elif len(matches) == 1 or matches[0][1].score >= AMBIGUITY_RATIO * matches[1][1].score:
            o.evidence = matches[0][1].as_dict()
            matches[0][0].obs.append(o)
        else:
            o.evidence = {"created_run": True, "unresolved": True}
            groups.append(Group([o], unresolved=True, candidates=matches))
    return groups


def assign_runs(groups: list[Group], live_run_ids: set[int]) -> tuple[list[int | None], dict[int, int]]:
    """The run each group keeps (None: needs a new one), and for each run no group keeps, the index of
    the group that received most of its observations (it is merged into that group's run)."""
    claimed: set[int] = set()
    keepers: list[int | None] = []
    for g in groups:  # cluster() creates groups in the order of their first observation
        counts = Counter(o.home_run for o in g.obs if o.home_run in live_run_ids)
        keeper = next((r for r, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])) if r not in claimed), None)
        if keeper is not None:
            claimed.add(keeper)
        keepers.append(keeper)
    vacated: dict[int, int] = {}
    for run_id in sorted(live_run_ids - claimed):
        received = Counter(i for i, g in enumerate(groups) for o in g.obs if o.home_run == run_id)
        if received:
            vacated[run_id] = sorted(received.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    return keepers, vacated


# --- Loading -------------------------------------------------------------------------------------------


def _linked_obs(rows) -> list[Obs]:
    out = []
    for raw, link, run in rows:
        obs = DungeonRunObservation.model_validate(raw.payload)
        identities = (link.match_evidence or {}).get("identities") or {}
        out.append(facts(raw, obs, identities, namespace_id=run.namespace_id, dungeon_id=run.dungeon_id, run_id=link.run_id))
    return out


def _linked_query():
    return (
        select(RawObservation, RunObservation, DungeonRun)
        .join(RunObservation, RunObservation.raw_observation_id == RawObservation.id)
        .join(DungeonRun, DungeonRun.id == RunObservation.run_id)
        .where(RawObservation.status == "accepted", RawObservation.type == "dungeon_run")
    )


def _related(a: Obs, b: Obs, pad: timedelta) -> bool:
    if a.start > b.end + pad or b.start > a.end + pad:
        return False
    return bool(a.members.keys() & b.members.keys()) or bool(a.party_guid and a.party_guid == b.party_guid)


def neighbourhood(db: Session, seed: Obs, settings: Settings, extra_run_ids: set[int] = frozenset()) -> list[Obs]:
    """``seed`` plus every accepted observation it could be matched with, transitively."""
    pad = timedelta(seconds=settings.match_time_padding_seconds)
    found: dict[int, Obs] = {seed.raw_id: seed}
    lo, hi = seed.start - pad, seed.end + pad
    queried: tuple[datetime, datetime] | None = None
    pool: dict[int, Obs] = {}
    while queried != (lo, hi):
        queried = (lo, hi)
        rows = db.execute(
            _linked_query().where(
                DungeonRun.namespace_id == seed.namespace_id,
                DungeonRun.dungeon_id == seed.dungeon_id,
                RawObservation.is_synthetic.is_(seed.synthetic),
                RawObservation.observed_start <= hi,
                RawObservation.observed_end >= lo,
            )
        ).all()
        pool.update({o.raw_id: o for o in _linked_obs(rows) if o.raw_id not in found and o.raw_id not in pool})
        frontier = list(found.values())
        while frontier:
            current = frontier.pop()
            for raw_id, cand in list(pool.items()):
                if _related(current, cand, pad):
                    found[raw_id] = pool.pop(raw_id)
                    frontier.append(cand)
        lo = min(o.start for o in found.values()) - pad
        hi = max(o.end for o in found.values()) + pad
        lo, hi = min(lo, queried[0]), max(hi, queried[1])
    # Every observation already in a run involved here, so a run is never half re-examined.
    run_ids = sorted({o.run_id for o in found.values() if o.run_id is not None} | set(extra_run_ids))
    if run_ids:
        rows = db.execute(_linked_query().where(RunObservation.run_id.in_(run_ids))).all()
        for o in _linked_obs(rows):
            found.setdefault(o.raw_id, o)
    return list(found.values())


# --- Applying ------------------------------------------------------------------------------------------


@dataclass
class Outcome:
    touched_runs: set[int]
    run_of: dict[int, int]  # raw observation id -> run id


def apply(db: Session, observations: list[Obs], settings: Settings, extra_run_ids: set[int] = frozenset()) -> Outcome:
    """Cluster ``observations`` and make the links, runs and review candidates agree with the result.

    The caller rebuilds ``touched_runs``.
    """
    groups = cluster(observations, settings)
    live = {o.home_run for o in observations if o.home_run is not None} | set(extra_run_ids)
    live = {rid for rid in live if (run := db.get(DungeonRun, rid)) is not None and run.merged_into_id is None}
    keepers, vacated = assign_runs(groups, live)
    for i, g in enumerate(groups):
        if keepers[i] is None:
            first = min(g.obs, key=lambda o: o.order)
            run = DungeonRun(
                namespace_id=first.namespace_id,
                dungeon_id=first.dungeon_id,
                difficulty_id=first.difficulty_id,
                started_at=first.start,
                last_observed_at=first.end,
                party_guid=first.party_guid,
                is_synthetic=first.synthetic,
            )
            db.add(run)
            db.flush()
            keepers[i] = run.id
    runs_by_public = {}
    links = {
        link.raw_observation_id: link
        for link in db.scalars(select(RunObservation).where(RunObservation.raw_observation_id.in_([o.raw_id for o in observations])))
    }
    run_of: dict[int, int] = {}
    for i, g in enumerate(groups):
        target = keepers[i]
        for o in g.obs:
            run_of[o.raw_id] = target
            evidence = {**o.evidence, "identities": {k: v for k, v in o.identities.items()}}
            link = links.get(o.raw_id)
            if link is None:
                db.add(RunObservation(run_id=target, raw_observation_id=o.raw_id, match_score=evidence.get("score", 0.0), match_evidence=evidence))
            elif link.run_id != target:
                moved = list((link.match_evidence or {}).get("moved_from", []))
                previous = runs_by_public.setdefault(link.run_id, db.get(DungeonRun, link.run_id).public_id)
                link.match_evidence = {**evidence, "moved_from": [*moved, previous]}
                link.match_score = evidence.get("score", 0.0)
                link.run_id = target
    for run_id, group_index in vacated.items():
        db.get(DungeonRun, run_id).merged_into_id = keepers[group_index]

    # Review candidates: recomputed for these observations; decisions a reviewer took are kept.
    ids = [o.raw_id for o in observations]
    db.execute(delete(RunMatchCandidate).where(RunMatchCandidate.raw_observation_id.in_(ids), RunMatchCandidate.status == "unresolved"))
    index_of = {id(g): i for i, g in enumerate(groups)}
    for g in groups:
        if g.unresolved:
            (o,) = g.obs
            for candidate, ev in g.candidates:
                db.add(
                    RunMatchCandidate(
                        raw_observation_id=o.raw_id, candidate_run_id=keepers[index_of[id(candidate)]], score=ev.score, evidence=ev.as_dict()
                    )
                )
    db.flush()
    return Outcome(touched_runs=set(keepers) | set(vacated) | live, run_of=run_of)


# --- Whole-database preview / repair (python -m app.cli rematch) ----------------------------------------


@dataclass
class Change:
    kind: str  # move | merge | new_run | unresolved
    detail: dict


def plan_all(db: Session, settings: Settings) -> tuple[list[tuple[list[Obs], list[Group], list[int | None], dict[int, int]]], list[Change]]:
    """Cluster every accepted dungeon_run observation and list what would change. Writes nothing."""
    rows = db.execute(_linked_query().where(DungeonRun.merged_into_id.is_(None))).all()
    by_area: dict[tuple, list[Obs]] = defaultdict(list)
    for o in _linked_obs(rows):
        by_area[(o.namespace_id, o.dungeon_id, o.synthetic)].append(o)
    public = dict(db.execute(select(DungeonRun.id, DungeonRun.public_id)).all())
    keys = {o.raw_id: o.observation_key for area in by_area.values() for o in area}
    plans, changes = [], []
    for area in sorted(by_area, key=str):
        observations = by_area[area]
        groups = cluster(observations, settings)
        live = {o.run_id for o in observations}
        keepers, vacated = assign_runs(groups, live)
        plans.append((observations, groups, keepers, vacated))
        for i, g in enumerate(groups):
            target = public.get(keepers[i]) if keepers[i] is not None else f"new run #{i + 1}"
            if keepers[i] is None:
                changes.append(Change("new_run", {"for": [keys[o.raw_id] for o in g.obs], "run": target}))
            for o in g.obs:
                if o.run_id != keepers[i]:
                    changes.append(
                        Change("move", {"observation": keys[o.raw_id], "raw_id": o.raw_id, "from": public[o.run_id], "to": target, "evidence": o.evidence})
                    )
            if g.unresolved:
                changes.append(Change("unresolved", {"observation": keys[g.obs[0].raw_id], "run": target}))
        for run_id, group_index in vacated.items():
            target = public.get(keepers[group_index]) if keepers[group_index] is not None else f"new run #{group_index + 1}"
            changes.append(Change("merge", {"run": public[run_id], "into": target}))
    return plans, changes


def apply_all(db: Session, settings: Settings) -> set[int]:
    """Apply :func:`plan_all`. For disposable copies and approved repairs only. Returns touched run IDs."""
    touched: set[int] = set()
    plans, _ = plan_all(db, settings)
    for observations, _groups, _keepers, _vacated in plans:
        touched |= apply(db, observations, settings).touched_runs
    return touched
