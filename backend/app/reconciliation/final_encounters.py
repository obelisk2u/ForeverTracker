"""Which boss kill finishes each dungeon (final_encounters.json).

Groups formed outside the dungeon finder never get a completion event, so a run that kills the
dungeon's final boss counts as completed with "probable" confidence.
"""

from __future__ import annotations

import json
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
