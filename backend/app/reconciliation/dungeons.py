from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Dungeon
from app.reconciliation.final_encounters import Wing, wing_for
from app.schemas.observations import DungeonRunObservation, InstanceInfo


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower().replace("'", "")).strip("-")
    return slug[:70] or "dungeon"


def _new_dungeon(db: Session, *, map_id: int, wing: str, name: str, instance_type: str, max_players, synthetic: bool) -> Dungeon:
    slug = slugify(name)
    if db.scalar(select(Dungeon.id).where(Dungeon.slug == slug)) is not None:
        slug = f"{slug}-{map_id}"
    dungeon = Dungeon(
        map_id=map_id,
        wing=wing,
        slug=slug,
        name=name,
        instance_type=instance_type,
        max_players=max_players,
        is_synthetic=synthetic,
    )
    db.add(dungeon)
    db.flush()
    return dungeon


def get_or_create_dungeon(db: Session, instance: InstanceInfo, *, synthetic: bool, wing: Wing | None = None) -> Dungeon:
    """Dungeons are keyed by the client's instance map ID (the 8th return of GetInstanceInfo), and by
    wing where a dungeon's wings share one map. The whole dungeon's row always exists."""
    dungeon = db.scalar(select(Dungeon).where(Dungeon.map_id == instance.map_id, Dungeon.wing == ""))
    if dungeon is not None:
        if dungeon.catalog_status == "observed" and instance.name and dungeon.name.startswith("Unknown dungeon"):
            dungeon.name = instance.name
    else:
        dungeon = _new_dungeon(
            db,
            map_id=instance.map_id,
            wing="",
            name=instance.name or f"Unknown dungeon {instance.map_id}",
            instance_type=instance.instance_type,
            max_players=instance.max_players,
            synthetic=synthetic,
        )
    return wing_dungeon(db, dungeon, wing)


def wing_dungeon(db: Session, dungeon: Dungeon, wing: Wing | None) -> Dungeon:
    """The row for ``wing`` of ``dungeon``'s map (the whole dungeon for None), created from the whole
    dungeon's row when missing."""
    key = wing.key if wing else ""
    if dungeon.wing == key:
        return dungeon
    row = db.scalar(select(Dungeon).where(Dungeon.map_id == dungeon.map_id, Dungeon.wing == key))
    if row is not None or wing is None:
        return row or dungeon  # the whole dungeon's row exists whenever a wing's does
    base = dungeon if dungeon.wing == "" else db.scalar(select(Dungeon).where(Dungeon.map_id == dungeon.map_id, Dungeon.wing == ""))
    base = base or dungeon
    base_name = base.name if base.wing == "" else f"Unknown dungeon {base.map_id}"
    return _new_dungeon(
        db,
        map_id=base.map_id,
        wing=wing.key,
        name=f"{base_name}: {wing.name}",
        instance_type=base.instance_type,
        max_players=base.max_players,
        synthetic=base.is_synthetic,
    )


def observation_wing(obs: DungeonRunObservation) -> Wing | None:
    """The wing an observation was in, from the bosses it pulled (in pull order)."""
    return wing_for(obs.instance.map_id, (e.encounter_id for e in sorted(obs.encounters, key=lambda e: e.started_at)))
