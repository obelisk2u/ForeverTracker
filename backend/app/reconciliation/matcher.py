"""Multi-observer run matching.

Several addon users in one group each upload their own record of the same dungeon run. This
module decides, conservatively, whether an incoming observation describes a run that already
exists. See docs/IDENTITY_AND_RECONCILIATION.md for the full rules and their rationale.

Evidence (per candidate canonical run):

* **vetoes** — any one prevents a match: different party GUIDs, different difficulty, the same
  boss killed at incompatible times (two different instance copies).
* **shared characters** — characters identified in both records whose presence intervals
  overlap by at least ``MIN_OVERLAP_SECONDS``. A character cannot be in two instances at once,
  so overlapping presence is the core signal.
* **party GUID equality** and **aligned boss encounters** add confidence.

A match needs no veto and either ``match_min_shared_characters`` shared characters, or an
identical party GUID plus one shared character. When several runs match and none is clearly
best, the observation becomes its own run marked ``unresolved`` and the candidates are kept
for review instead of guessed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import DungeonRun, RawObservation, RunEncounter, RunMatchCandidate, RunObservation, RunParticipant
from app.models.base import from_epoch
from app.schemas.observations import DungeonRunObservation

MIN_OVERLAP_SECONDS = 60
ENCOUNTER_ALIGN_SECONDS = 120
ENCOUNTER_CONFLICT_SECONDS = 600
AMBIGUITY_RATIO = 1.5


@dataclass
class ObservedMember:
    character_id: int
    intervals: list[tuple[datetime, datetime]]


@dataclass
class MatchEvidence:
    run_id: int
    score: float = 0.0
    shared_characters: list[int] = field(default_factory=list)
    party_guid_match: bool = False
    aligned_encounters: int = 0
    time_overlap_ratio: float = 0.0
    vetoes: list[str] = field(default_factory=list)

    @property
    def vetoed(self) -> bool:
        return bool(self.vetoes)

    def as_dict(self) -> dict:
        return {
            "score": round(self.score, 3),
            "shared_characters": self.shared_characters,
            "party_guid_match": self.party_guid_match,
            "aligned_encounters": self.aligned_encounters,
            "time_overlap_ratio": round(self.time_overlap_ratio, 3),
            "vetoes": self.vetoes,
        }


def observation_window(obs: DungeonRunObservation) -> tuple[datetime, datetime]:
    end = obs.timing.ended_at if obs.timing.ended_at is not None else obs.timing.last_updated_at
    return from_epoch(obs.timing.started_at), from_epoch(end)


def member_intervals(obs: DungeonRunObservation, ref: str) -> list[tuple[datetime, datetime]]:
    _, window_end = observation_window(obs)
    for member in obs.roster:
        if member.ref == ref:
            out = []
            for p in member.presence:
                start = from_epoch(p.start)
                end = from_epoch(p.end) if p.end is not None else window_end
                if end > start:
                    out.append((start, end))
            if not out:
                out.append(observation_window(obs))
            return out
    return []


def _overlap_seconds(a: tuple[datetime, datetime], b: tuple[datetime, datetime]) -> float:
    return max(0.0, (min(a[1], b[1]) - max(a[0], b[0])).total_seconds())


def evaluate_candidate(
    db: Session,
    run: DungeonRun,
    obs: DungeonRunObservation,
    members: list[ObservedMember],
    settings: Settings,
) -> MatchEvidence:
    ev = MatchEvidence(run_id=run.id)
    if obs.party_guid and run.party_guid:
        if obs.party_guid == run.party_guid:
            ev.party_guid_match = True
        else:
            ev.vetoes.append("party_guid_mismatch")
    if obs.instance.difficulty_id is not None and run.difficulty_id is not None:
        if obs.instance.difficulty_id != run.difficulty_id:
            ev.vetoes.append("difficulty_mismatch")

    run_end = run.ended_at or run.last_observed_at
    participants = db.scalars(select(RunParticipant).where(RunParticipant.run_id == run.id)).all()
    by_char = {p.character_id: p for p in participants}
    for member in members:
        p = by_char.get(member.character_id)
        if p is None:
            continue
        p_interval = (p.joined_at or run.started_at, p.left_at or run_end)
        if sum(_overlap_seconds(i, p_interval) for i in member.intervals) >= MIN_OVERLAP_SECONDS:
            ev.shared_characters.append(member.character_id)

    run_encounters = db.scalars(select(RunEncounter).where(RunEncounter.run_id == run.id)).all()
    for enc in obs.encounters:
        start = from_epoch(enc.started_at)
        same_boss = [e for e in run_encounters if e.encounter_id == enc.encounter_id]
        if any(abs((e.started_at - start).total_seconds()) <= ENCOUNTER_ALIGN_SECONDS for e in same_boss):
            ev.aligned_encounters += 1
        elif enc.success and any(
            e.success and abs((e.started_at - start).total_seconds()) > ENCOUNTER_CONFLICT_SECONDS for e in same_boss
        ):
            ev.vetoes.append("boss_killed_at_different_times")

    o_start, o_end = observation_window(obs)
    shortest = min((o_end - o_start).total_seconds(), (run_end - run.started_at).total_seconds())
    overlap = _overlap_seconds((o_start, o_end), (run.started_at, run_end))
    ev.time_overlap_ratio = overlap / shortest if shortest > 0 else (1.0 if overlap >= 0 else 0.0)

    ev.score = (
        2.0 * len(ev.shared_characters)
        + (3.0 if ev.party_guid_match else 0.0)
        + 1.0 * ev.aligned_encounters
        + ev.time_overlap_ratio
    )
    return ev


def is_match(ev: MatchEvidence, settings: Settings) -> bool:
    if ev.vetoed:
        return False
    if len(ev.shared_characters) >= settings.match_min_shared_characters:
        return True
    return ev.party_guid_match and len(ev.shared_characters) >= 1


def find_candidates(
    db: Session, namespace_id: int, dungeon_id: int, obs: DungeonRunObservation, synthetic: bool, settings: Settings
) -> list[DungeonRun]:
    start, end = observation_window(obs)
    pad = timedelta(seconds=settings.match_time_padding_seconds)
    run_end = func.coalesce(DungeonRun.ended_at, DungeonRun.last_observed_at)
    return list(
        db.scalars(
            select(DungeonRun).where(
                DungeonRun.namespace_id == namespace_id,
                DungeonRun.dungeon_id == dungeon_id,
                DungeonRun.is_synthetic == synthetic,
                DungeonRun.merged_into_id.is_(None),
                DungeonRun.quarantined.is_(False),
                DungeonRun.started_at <= end + pad,
                run_end >= start - pad,
            )
        )
    )


@dataclass
class MatchDecision:
    run: DungeonRun | None
    evidence: MatchEvidence | None
    unresolved_candidates: list[MatchEvidence] = field(default_factory=list)


def decide(
    db: Session,
    namespace_id: int,
    dungeon_id: int,
    obs: DungeonRunObservation,
    members: list[ObservedMember],
    synthetic: bool,
    settings: Settings,
    preferred_run_id: int | None,
) -> MatchDecision:
    evaluations = [
        evaluate_candidate(db, run, obs, members, settings)
        for run in find_candidates(db, namespace_id, dungeon_id, obs, synthetic, settings)
    ]
    matches = sorted((e for e in evaluations if is_match(e, settings)), key=lambda e: e.score, reverse=True)
    if preferred_run_id is not None:
        for ev in evaluations:
            # An earlier revision of this very observation already lives in this run.
            if ev.run_id == preferred_run_id and not ev.vetoed:
                return MatchDecision(db.get(DungeonRun, ev.run_id), ev)
    if not matches:
        return MatchDecision(None, None)
    if len(matches) == 1 or matches[0].score >= AMBIGUITY_RATIO * matches[1].score:
        return MatchDecision(db.get(DungeonRun, matches[0].run_id), matches[0])
    return MatchDecision(None, None, unresolved_candidates=matches)


def link(db: Session, run: DungeonRun, raw: RawObservation, evidence: MatchEvidence | None, identities: dict[str, int]) -> None:
    db.add(
        RunObservation(
            run_id=run.id,
            raw_observation_id=raw.id,
            match_score=evidence.score if evidence else 0.0,
            match_evidence={**(evidence.as_dict() if evidence else {"created_run": True}), "identities": identities},
        )
    )


def record_unresolved(db: Session, raw: RawObservation, candidates: list[MatchEvidence]) -> None:
    for ev in candidates:
        db.add(RunMatchCandidate(raw_observation_id=raw.id, candidate_run_id=ev.run_id, score=ev.score, evidence=ev.as_dict()))
