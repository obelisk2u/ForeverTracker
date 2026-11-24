"""Completions that stored runs gain when a final boss is added to final_encounters.json.

A run's outcome is derived when the run is rebuilt (an upload that touches it, a moderation action or
``rebuild``), so a newly listed final boss does not change runs stored before it. Their observations keep
every boss kill, so the evidence is still there. This module finds the runs a confirmed final-boss kill
would complete and, only on request, completes them:

* only runs whose stored outcome is ``left``, ``disconnected`` or ``unknown``;
* only when deriving the outcome again, by the same rule ingestion uses (``consolidate._outcome``),
  gives ``completed`` with ``probable`` confidence, i.e. a successful kill of a listed final boss;
* only the outcome fields change. Raw observations, matching and metrics are left as they are.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Dungeon, DungeonRun, RunEncounter, RunParticipant
from app.reconciliation.consolidate import _load_links, _outcome
from app.reconciliation.final_encounters import final_encounters

RECOVERABLE_OUTCOMES = ("left", "disconnected", "unknown")


@dataclass(frozen=True)
class Recovery:
    run_id: int
    public_id: str
    dungeon: str
    map_id: int
    outcome: str
    new_outcome: tuple[str, str]
    evidence: list

    def report(self) -> dict:
        return {
            "run": self.public_id,
            "dungeon": self.dungeon,
            "map_id": self.map_id,
            "stored": self.outcome,
            "would_be": list(self.new_outcome),
            "evidence": self.evidence,
        }


def find(db: Session) -> list[Recovery]:
    """Stored runs that a listed final-boss kill would complete. Writes nothing."""
    rows = db.execute(
        select(DungeonRun, Dungeon)
        .join(Dungeon, Dungeon.id == DungeonRun.dungeon_id)
        .where(DungeonRun.outcome.in_(RECOVERABLE_OUTCOMES), DungeonRun.merged_into_id.is_(None))
        .order_by(DungeonRun.id)
    ).all()
    out: list[Recovery] = []
    for run, dungeon in rows:
        finals = final_encounters(dungeon)
        if not finals:
            continue
        encounters = list(db.scalars(select(RunEncounter).where(RunEncounter.run_id == run.id).order_by(RunEncounter.started_at)))
        if not any(e.success and e.encounter_id in finals for e in encounters):
            continue
        outcome, confidence, evidence = _outcome(_load_links(db, run.id), dungeon, encounters)
        if (outcome, confidence) != ("completed", "probable"):
            continue
        out.append(Recovery(run.id, run.public_id, dungeon.name, dungeon.map_id, run.outcome, (outcome, confidence), evidence))
    return out


def apply(db: Session, recoveries: list[Recovery], settings: Settings) -> set[int]:
    """Give each run its recovered outcome and recompute its participants' statistics. Returns those characters."""
    from app.analytics.character_stats import recompute_many

    characters: set[int] = set()
    for r in recoveries:
        run = db.get(DungeonRun, r.run_id)
        if run is None or run.outcome not in RECOVERABLE_OUTCOMES:
            continue
        run.outcome, run.completion_confidence = r.new_outcome
        run.outcome_evidence = r.evidence
        characters |= set(db.scalars(select(RunParticipant.character_id).where(RunParticipant.run_id == run.id)))
    db.flush()
    recompute_many(db, characters, settings)
    return characters
