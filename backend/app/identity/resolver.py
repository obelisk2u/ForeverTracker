"""Evidence-based character identity resolution.

Rules (docs/IDENTITY_AND_RECONCILIATION.md):

1. A GUID seen in a namespace belongs to exactly one character (enforced by a partial unique index).
   A GUID observation links to that character even if the name differs (a rename), and records
   the new name as additional evidence.
2. A GUID whose recorded class differs from the character's class is a contradiction: the
   observation is quarantined, never merged.
3. A name without a GUID is weak evidence. It links only when exactly one class-compatible
   character held that name around that time. Otherwise the roster entry stays unresolved:
   ForeverTracker would rather show "unidentified participant" than merge two people.
4. A GUID observation may upgrade a single name-only character with the same name and class.
5. Synthetic (simulator) data never links to real characters, and vice versa.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.identity.names import full_name, normalize_full_name
from app.models import Character, CharacterIdentityEvidence

NAME_ONLY_TIME_TOLERANCE = timedelta(days=30)


class IdentityConflict(Exception):
    def __init__(self, reason: str, detail: str = ""):
        self.reason = reason
        super().__init__(f"{reason}: {detail}" if detail else reason)


@dataclass(frozen=True)
class Subject:
    guid: str | None
    name: str | None
    surname: str | None
    identity_status: str = "ok"
    class_file: str | None = None
    race_file: str | None = None
    level: int | None = None
    realm_label: str | None = None


@dataclass
class IdentityCache:
    """Evidence and candidates for one observation's roster, loaded in a few queries.

    Authoritative for the GUIDs and normalised names it was built for; new evidence and new
    characters are added to it as they are created.
    """

    guid_evidence: dict[str, CharacterIdentityEvidence] = field(default_factory=dict)
    evidence: dict[tuple[int, str, str], CharacterIdentityEvidence] = field(default_factory=dict)
    by_name: dict[str, list[Character]] = field(default_factory=dict)

    @classmethod
    def preload(cls, db: Session, namespace_id: int, subjects: list["Subject"], synthetic: bool) -> "IdentityCache":
        cache = cls()
        guids = sorted({s.guid for s in subjects if s.guid and s.identity_status == "ok"})
        names = sorted({normalize_full_name(s.name, s.surname) for s in subjects if s.name and s.identity_status == "ok"})
        conds = []
        if guids:
            conds.append(and_(CharacterIdentityEvidence.kind == "guid", CharacterIdentityEvidence.value.in_(guids)))
        if names:
            conds.append(and_(CharacterIdentityEvidence.kind == "name", CharacterIdentityEvidence.value.in_(names)))
        char_ids: set[int] = set()
        if conds:
            for ev in db.scalars(
                select(CharacterIdentityEvidence).where(CharacterIdentityEvidence.namespace_id == namespace_id, or_(*conds))
            ):
                cache.evidence[(ev.character_id, ev.kind, ev.value)] = ev
                if ev.kind == "guid":
                    cache.guid_evidence[ev.value] = ev
                char_ids.add(ev.character_id)
        for name in names:
            cache.by_name[name] = []
        if names or char_ids:
            stmt = select(Character).where(
                Character.namespace_id == namespace_id,
                or_(Character.full_name_normalized.in_(names), Character.id.in_(sorted(char_ids))),
            )
            for c in db.scalars(stmt):
                if c.full_name_normalized in cache.by_name and c.is_synthetic == synthetic and c.merged_into_id is None:
                    cache.by_name[c.full_name_normalized].append(c)
        return cache


@dataclass
class Resolution:
    character: Character | None
    strength: str | None  # "guid" | "name" | None
    created: bool = False
    flags: list[str] = field(default_factory=list)


def _canonical(db: Session, character: Character) -> Character:
    seen = set()
    while character.merged_into_id is not None and character.id not in seen:
        seen.add(character.id)
        character = db.get(Character, character.merged_into_id)
    return character


def _class_compatible(character: Character, subject: Subject) -> bool:
    return not (character.class_file and subject.class_file and character.class_file != subject.class_file)


def _touch(db: Session, character: Character, subject: Subject, observed_at: datetime, *, update_name: bool) -> None:
    if observed_at < character.first_observed_at:
        character.first_observed_at = observed_at
    newer = observed_at >= character.last_observed_at
    if newer:
        character.last_observed_at = observed_at
        if subject.realm_label:
            character.realm_label = subject.realm_label
    if update_name and newer and subject.name:
        character.name = subject.name
        character.surname = subject.surname
        character.full_name = full_name(subject.name, subject.surname)
        character.full_name_normalized = normalize_full_name(subject.name, subject.surname)
    if character.class_file is None and subject.class_file:
        character.class_file = subject.class_file
    if character.race_file is None and subject.race_file:
        character.race_file = subject.race_file
    if subject.level is not None and (character.latest_level_at is None or observed_at >= character.latest_level_at):
        character.latest_level = subject.level
        character.latest_level_at = observed_at


def _add_evidence(
    db: Session,
    character: Character,
    kind: str,
    value: str,
    display: str | None,
    strength: str,
    observed_at: datetime,
    cache: "IdentityCache | None" = None,
) -> None:
    key = (character.id, kind, value)
    if cache is not None:
        ev = cache.evidence.get(key)
    else:
        ev = db.scalar(
            select(CharacterIdentityEvidence).where(
                CharacterIdentityEvidence.character_id == character.id,
                CharacterIdentityEvidence.kind == kind,
                CharacterIdentityEvidence.value == value,
            )
        )
    if ev is None:
        ev = CharacterIdentityEvidence(
            character_id=character.id,
            namespace_id=character.namespace_id,
            kind=kind,
            value=value,
            display_value=display,
            strength=strength,
            observation_count=1,
            first_seen_at=observed_at,
            last_seen_at=observed_at,
        )
        db.add(ev)
        if cache is not None:
            cache.evidence[key] = ev
            if kind == "guid":
                cache.guid_evidence[value] = ev
    else:
        ev.observation_count += 1
        ev.first_seen_at = min(ev.first_seen_at, observed_at)
        ev.last_seen_at = max(ev.last_seen_at, observed_at)
        if strength == "strong":
            ev.strength = "strong"


def _create(db: Session, namespace_id: int, subject: Subject, observed_at: datetime, synthetic: bool) -> Character:
    assert subject.name
    character = Character(
        namespace_id=namespace_id,
        name=subject.name,
        surname=subject.surname,
        full_name=full_name(subject.name, subject.surname),
        full_name_normalized=normalize_full_name(subject.name, subject.surname),
        realm_label=subject.realm_label,
        class_file=subject.class_file,
        race_file=subject.race_file,
        latest_level=subject.level,
        latest_level_at=observed_at if subject.level is not None else None,
        first_observed_at=observed_at,
        last_observed_at=observed_at,
        identity_confidence="guid_confirmed" if subject.guid else "name_only",
        is_synthetic=synthetic,
    )
    db.add(character)
    db.flush()
    return character


def _name_candidates(
    db: Session, namespace_id: int, normalized: str, synthetic: bool, cache: "IdentityCache | None" = None
) -> list[Character]:
    if cache is not None and normalized in cache.by_name:
        return [c for c in cache.by_name[normalized] if c.merged_into_id is None and c.full_name_normalized == normalized]
    return list(
        db.scalars(
            select(Character).where(
                Character.namespace_id == namespace_id,
                Character.full_name_normalized == normalized,
                Character.is_synthetic == synthetic,
                Character.merged_into_id.is_(None),
            )
        )
    )


def _name_evidence_distance(
    db: Session, character: Character, normalized: str, observed_at: datetime, cache: "IdentityCache | None" = None
) -> timedelta:
    if cache is not None:
        ev = cache.evidence.get((character.id, "name", normalized))
    else:
        ev = db.scalar(
            select(CharacterIdentityEvidence).where(
                CharacterIdentityEvidence.character_id == character.id,
                CharacterIdentityEvidence.kind == "name",
                CharacterIdentityEvidence.value == normalized,
            )
        )
    if ev is None:
        return timedelta.max
    if ev.first_seen_at <= observed_at <= ev.last_seen_at:
        return timedelta(0)
    return min(abs(observed_at - ev.first_seen_at), abs(observed_at - ev.last_seen_at))


def resolve_character(
    db: Session,
    namespace_id: int,
    subject: Subject,
    observed_at: datetime,
    *,
    synthetic: bool,
    cache: IdentityCache | None = None,
) -> Resolution:
    """Find or create the character an observed roster entry refers to.

    Raises :class:`IdentityConflict` when the evidence contradicts itself.
    """
    if subject.identity_status != "ok" or not subject.name:
        return Resolution(None, None, flags=["identity_unavailable"])

    normalized = normalize_full_name(subject.name, subject.surname)
    display = full_name(subject.name, subject.surname)

    if subject.guid:
        if cache is not None:
            ev = cache.guid_evidence.get(subject.guid)
        else:
            ev = db.scalar(
                select(CharacterIdentityEvidence).where(
                    CharacterIdentityEvidence.namespace_id == namespace_id,
                    CharacterIdentityEvidence.kind == "guid",
                    CharacterIdentityEvidence.value == subject.guid,
                )
            )
        if ev is not None:
            character = _canonical(db, db.get(Character, ev.character_id))
            if character.is_synthetic != synthetic:
                raise IdentityConflict("synthetic_mismatch", subject.guid)
            if not _class_compatible(character, subject):
                raise IdentityConflict(
                    "guid_class_conflict", f"{subject.guid} is {character.class_file}, observed {subject.class_file}"
                )
            flags: list[str] = []
            ev.observation_count += 1
            ev.last_seen_at = max(ev.last_seen_at, observed_at)
            ev.first_seen_at = min(ev.first_seen_at, observed_at)
            if normalized != character.full_name_normalized:
                flags.append("name_changed")
            _add_evidence(db, character, "name", normalized, display, "strong", observed_at, cache)
            _touch(db, character, subject, observed_at, update_name=True)
            return Resolution(character, "guid", flags=flags)

        compatible = [
            c
            for c in _name_candidates(db, namespace_id, normalized, synthetic, cache)
            if c.identity_confidence == "name_only" and _class_compatible(c, subject)
        ]
        flags = []
        if len(compatible) == 1:
            character = compatible[0]
            character.identity_confidence = "guid_confirmed"
            flags.append("upgraded_name_only")
            created = False
        else:
            character = _create(db, namespace_id, subject, observed_at, synthetic)
            created = True
            if cache is not None:
                cache.by_name.setdefault(normalized, []).append(character)
            if len(compatible) > 1:
                flags.append("ambiguous_name_only_candidates")
        _add_evidence(db, character, "guid", subject.guid, None, "strong", observed_at, cache)
        _add_evidence(db, character, "name", normalized, display, "strong", observed_at, cache)
        _touch(db, character, subject, observed_at, update_name=not created)
        db.flush()
        return Resolution(character, "guid", created=created, flags=flags)

    # Name-only evidence.
    compatible = [c for c in _name_candidates(db, namespace_id, normalized, synthetic, cache) if _class_compatible(c, subject)]
    if not compatible:
        character = _create(db, namespace_id, subject, observed_at, synthetic)
        if cache is not None:
            cache.by_name.setdefault(normalized, []).append(character)
        _add_evidence(db, character, "name", normalized, display, "weak", observed_at, cache)
        return Resolution(character, "name", created=True, flags=["name_only"])
    if len(compatible) > 1:
        ranked = sorted(compatible, key=lambda c: _name_evidence_distance(db, c, normalized, observed_at, cache))
        best, second = ranked[0], ranked[1]
        d_best = _name_evidence_distance(db, best, normalized, observed_at, cache)
        d_second = _name_evidence_distance(db, second, normalized, observed_at, cache)
        if not (d_best <= NAME_ONLY_TIME_TOLERANCE < d_second):
            return Resolution(None, None, flags=["ambiguous_name"])
        compatible = [best]
    character = compatible[0]
    _add_evidence(db, character, "name", normalized, display, "weak", observed_at, cache)
    _touch(db, character, subject, observed_at, update_name=False)
    return Resolution(character, "name", flags=["name_only"])
