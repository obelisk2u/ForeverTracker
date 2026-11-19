"""Which boss kill finishes each dungeon, and which wing a run was in (final_encounters.json).

Groups formed outside the dungeon finder never get a completion event, so a run that kills the
dungeon's final boss counts as completed with "probable" confidence.

Some dungeons' wings share one instance map ID (Scarlet Monastery's Graveyard, Library, Armory and
Cathedral): the client reports them as one dungeon, so a run's wing comes from the first of a wing's
bosses it pulled. A run that pulled none stays the whole dungeon.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from app.models import Dungeon

CATALOG = Path(__file__).with_name("final_encounters.json")


@cache
def catalog() -> dict[int, frozenset[int]]:
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    return {int(map_id): frozenset(int(e) for e in d["final"]) for map_id, d in data["dungeons"].items()}


def final_encounters(dungeon: Dungeon) -> frozenset[int]:
    """The dungeon's final bosses: from the catalog, or the curated column for a dungeon it lacks."""
    known = catalog().get(dungeon.map_id)
    if known:
        return known
    return frozenset({dungeon.final_encounter_id}) if dungeon.final_encounter_id is not None else frozenset()


@dataclass(frozen=True)
class Wing:
    key: str
    name: str
    encounters: frozenset[int]


@cache
def wing_catalog() -> dict[int, tuple[Wing, ...]]:
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    return {
        int(map_id): tuple(
            Wing(key, w["name"], frozenset(int(e) for e in w["encounters"])) for key, w in d["wings"].items()
        )
        for map_id, d in data["dungeons"].items()
        if d.get("wings")
    }


def wing_for(map_id: int, encounter_ids: Iterable[int]) -> Wing | None:
    """The wing of the first boss (in pull order) that belongs to one of the dungeon's wings, if any."""
    wings = wing_catalog().get(map_id)
    if not wings:
        return None
    for encounter_id in encounter_ids:
        for wing in wings:
            if encounter_id in wing.encounters:
                return wing
    return None
