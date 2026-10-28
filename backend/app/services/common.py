from __future__ import annotations

import string
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Character, CharacterStats, Dungeon, Namespace, ParticipantMetric
from app.schemas.api import CharacterSummary, DungeonRef, HiddenCharacter, MetricOut

SLOT_NAMES = {
    1: "Head", 2: "Neck", 3: "Shoulder", 4: "Shirt", 5: "Chest", 6: "Waist", 7: "Legs", 8: "Feet",
    9: "Wrist", 10: "Hands", 11: "Finger", 12: "Finger", 13: "Trinket", 14: "Trinket", 15: "Back",
    16: "Main Hand", 17: "Off Hand", 18: "Ranged", 19: "Tabard",
}


class NotFound(Exception):
    pass


class Suppressed(Exception):
    pass


def summarize(character: Character, namespace: Namespace, runs_observed: int | None) -> CharacterSummary:
    return CharacterSummary(
        id=character.public_id,
        namespace=namespace.slug,
        namespace_display=namespace.display_name,
        name=character.name,
        surname=character.surname,
        full_name=character.full_name,
        class_file=character.class_file,
        race_file=character.race_file,
        latest_level=character.latest_level,
        first_observed_at=character.first_observed_at,
        last_observed_at=character.last_observed_at,
        identity_confidence=character.identity_confidence,
        runs_observed=runs_observed or 0,
        is_synthetic=character.is_synthetic,
    )


def summaries(db: Session, settings: Settings, character_ids: Iterable[int]) -> dict[int, CharacterSummary | HiddenCharacter]:
    ids = list(set(character_ids))
    if not ids:
        return {}
    rows = db.execute(
        select(Character, Namespace, CharacterStats.runs_observed)
        .join(Namespace, Namespace.id == Character.namespace_id)
        .outerjoin(CharacterStats, CharacterStats.character_id == Character.id)
        .where(Character.id.in_(ids))
    ).all()
    out: dict[int, CharacterSummary | HiddenCharacter] = {}
    for character, namespace, runs_observed in rows:
        if character.visibility != "public" or (settings.environment == "production" and character.is_synthetic):
            out[character.id] = HiddenCharacter()
        else:
            out[character.id] = summarize(character, namespace, runs_observed)
    return out


def metric_out(m: ParticipantMetric) -> MetricOut:
    return MetricOut(
        metric=m.metric,
        value=m.value,
        unit=m.unit,
        source=m.source,
        status=m.status,
        coverage=m.coverage,
        resolution=m.resolution,
        confidence=m.confidence,
        contributors=m.contributor_count,
        derived=m.derived,
    )


def dungeon_ref(d: Dungeon) -> DungeonRef:
    return DungeonRef(slug=d.slug, name=d.name, map_id=d.map_id)


def observer_labels(contributor_ids: list[int]) -> dict[int, str]:
    """Public, per-run pseudonyms for contributors ("Observer A", "Observer B", ...)."""
    letters = string.ascii_uppercase
    labels: dict[int, str] = {}
    for cid in contributor_ids:
        if cid not in labels:
            i = len(labels)
            labels[cid] = f"Observer {letters[i % 26]}{'' if i < 26 else i // 26}"
    return labels
