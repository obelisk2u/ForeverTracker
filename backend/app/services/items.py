"""Item tooltips: what the game showed for an item, as the addon read it (0.2.13 and later).

A snapshot carries an item's tooltip the first time its installation sees that item. Each one is
stored as a report for the item, and an item shows the version the most installations report
(counting each installation's latest reading once), the most recent of equally common ones. A
tooltip whose first line is not the item's name in its link is not that item's and is dropped.

Tooltips are keyed by the item and what changes its tooltip (enchant, gems, suffix, bonuses), not by
who holds it: the link without its unique ID (kept with a negative suffix, which scales with it)
and the level and specialization it was linked at. The addon keys items the same way
(Inspect.itemKey).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import EquipmentSnapshot, ItemTooltipReport, RawObservation
from app.models.base import from_epoch
from app.schemas.observations import CharacterSnapshotObservation

_ITEM_STRING = re.compile(r"item:([-\d:]+)")
_NAME = re.compile(r"\[(.+?)\]")
# Colour, link, texture and atlas escapes in game text.
_ESCAPES = re.compile(r"\|c(?:[0-9a-fA-F]{8}|n[A-Za-z0-9_]+:)|\|r|\|H[^|]*\|h|\|h|\|T[^|]*\|t|\|A[^|]*\|a")


def item_key(link: str | None, item_id: int) -> str:
    m = _ITEM_STRING.search(link or "")
    if not m:
        return str(item_id)
    fields = m.group(1).split(":")
    fields += [""] * (10 - len(fields))
    try:
        negative_suffix = int(fields[6]) < 0
    except ValueError:
        negative_suffix = False
    if not negative_suffix:
        fields[7] = ""
    fields[8] = fields[9] = ""
    return ":".join(fields).rstrip(":")[:160]


def _clean(text: str | None) -> str | None:
    return None if text is None else _ESCAPES.sub("", text)


def record_tooltips(db: Session, raw: RawObservation, obs: CharacterSnapshotObservation, *, synthetic: bool) -> int:
    """Store the tooltips a snapshot carries. Returns how many were stored."""
    if obs.equipment is None:
        return 0
    stored: set[str] = set()
    for item in obs.equipment.items:
        if not item.tooltip:
            continue
        lines = [
            {"left": _clean(line.left) or "", "color": line.color, "right": _clean(line.right), "right_color": line.right_color}
            for line in item.tooltip
        ]
        title = lines[0]["left"].strip()
        name = _NAME.search(item.link or "")
        if not title or (name and title != (_clean(name.group(1)) or "").strip()):
            continue
        key = item_key(item.link, item.item_id)
        if key in stored:
            continue  # the same item in both ring or trinket slots
        stored.add(key)
        db.add(
            ItemTooltipReport(
                item_key=key,
                item_id=item.item_id,
                raw_observation_id=raw.id,
                contributor_id=raw.contributor_id,
                digest=hashlib.sha256(json.dumps(lines, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
                lines=lines,
                reported_at=from_epoch(obs.observed_at),
                is_synthetic=synthetic,
            )
        )
    return len(stored)


def forget_tooltips(db: Session, raw: RawObservation) -> None:
    db.execute(delete(ItemTooltipReport).where(ItemTooltipReport.raw_observation_id == raw.id))


def tooltips_for(db: Session, keys: Iterable[str]) -> dict[str, list[dict[str, Any]]]:
    """The tooltip each item shows, by item key; items without one are absent."""
    wanted = set(keys)
    if not wanted:
        return {}
    R = ItemTooltipReport
    rows = db.execute(
        select(R.id, R.item_key, R.contributor_id, R.digest, R.lines, R.reported_at)
        .where(R.item_key.in_(wanted))
        .order_by(R.reported_at, R.id)
    ).all()
    latest = {(r.item_key, r.contributor_id): r for r in rows}  # each installation's latest reading
    variants: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for (key, _), r in latest.items():
        variants[key][r.digest].append(r)
    out = {}
    for key, by_digest in variants.items():
        agreed = max(by_digest.values(), key=lambda rs: (len(rs), max((x.reported_at, x.id) for x in rs)))
        out[key] = max(agreed, key=lambda x: (x.reported_at, x.id)).lines
    return out


def snapshot_keys(snapshots: Iterable[EquipmentSnapshot]) -> set[str]:
    return {item_key(i.get("link"), i["item_id"]) for s in snapshots for i in s.items}
