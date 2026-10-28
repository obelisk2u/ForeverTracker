from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Dungeon
from app.schemas.observations import InstanceInfo


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower().replace("'", "")).strip("-")
    return slug[:70] or "dungeon"


def get_or_create_dungeon(db: Session, instance: InstanceInfo, *, synthetic: bool) -> Dungeon:
    """Dungeons are keyed by the client's instance map ID (the 8th return of GetInstanceInfo)."""
    dungeon = db.scalar(select(Dungeon).where(Dungeon.map_id == instance.map_id))
    if dungeon is not None:
        if dungeon.catalog_status == "observed" and instance.name and dungeon.name.startswith("Unknown dungeon"):
            dungeon.name = instance.name
        return dungeon
    name = instance.name or f"Unknown dungeon {instance.map_id}"
    slug = slugify(name)
    if db.scalar(select(Dungeon.id).where(Dungeon.slug == slug)) is not None:
        slug = f"{slug}-{instance.map_id}"
    dungeon = Dungeon(
        map_id=instance.map_id,
        slug=slug,
        name=name,
        instance_type=instance.instance_type,
        max_players=instance.max_players,
        is_synthetic=synthetic,
    )
    db.add(dungeon)
    db.flush()
    return dungeon
