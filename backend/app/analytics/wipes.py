"""Wipe detection.

* ``encounter_failed`` comes from the client's ENCOUNTER_END (success = 0). It is reported by
  the game, so it is not marked as inferred (it is still self-reported by the uploader).
* ``party_wipe`` is **inferred**: every participant present at that moment died within
  ``WIPE_WINDOW``. It is only as good as the death coverage of the run, and is labelled so.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

WIPE_WINDOW = timedelta(seconds=20)


@dataclass
class Presence:
    character_id: int
    joined_at: datetime | None
    left_at: datetime | None


@dataclass
class DeathPoint:
    character_id: int
    at: datetime


@dataclass
class EncounterPoint:
    encounter_id: int
    started_at: datetime
    ended_at: datetime | None
    success: bool | None


@dataclass
class Wipe:
    at: datetime
    kind: str
    inferred: bool
    encounter_id: int | None
    detail: str


def detect_wipes(
    presences: list[Presence],
    deaths: list[DeathPoint],
    encounters: list[EncounterPoint],
    *,
    death_coverage: str,
) -> list[Wipe]:
    wipes: list[Wipe] = []
    for enc in encounters:
        if enc.success is False:
            wipes.append(
                Wipe(
                    at=enc.ended_at or enc.started_at,
                    kind="encounter_failed",
                    inferred=False,
                    encounter_id=enc.encounter_id,
                    detail="Boss encounter ended without a kill (ENCOUNTER_END reported success = 0).",
                )
            )

    deaths = sorted(deaths, key=lambda d: d.at)
    last_wipe: datetime | None = None
    for i, first in enumerate(deaths):
        if last_wipe is not None and first.at - last_wipe <= WIPE_WINDOW:
            continue
        present = {
            p.character_id
            for p in presences
            if (p.joined_at is None or p.joined_at <= first.at) and (p.left_at is None or p.left_at >= first.at)
        }
        if len(present) < 2:
            continue
        died = {d.character_id for d in deaths[i:] if d.at - first.at <= WIPE_WINDOW}
        if present <= died:
            enc = next(
                (e for e in encounters if e.started_at <= first.at <= (e.ended_at or first.at + WIPE_WINDOW)), None
            )
            wipes.append(
                Wipe(
                    at=first.at,
                    kind="party_wipe",
                    inferred=True,
                    encounter_id=enc.encounter_id if enc else None,
                    detail=(
                        f"Inferred: all {len(present)} present party members died within {int(WIPE_WINDOW.total_seconds())} s."
                        + ("" if death_coverage == "complete" else " Death coverage for this run is incomplete.")
                    ),
                )
            )
            last_wipe = first.at
    return sorted(wipes, key=lambda w: w.at)
