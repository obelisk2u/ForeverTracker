"""Character namespaces: ``(game, region, ruleset)``.

The realm string is recorded as ``realm_label`` but never used for identity: Forever is
realmless and the client's realm value has not been observed at launch.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Namespace
from app.schemas.observations import NamespaceInfo

# GetCurrentRegion() values (Retail convention). Verified on Forever: no (launch checklist item).
REGION_BY_ID = {1: "us", 2: "kr", 3: "eu", 4: "tw", 5: "cn"}
KNOWN_REGIONS = frozenset(REGION_BY_ID.values())
RULESET_LABELS = {"pve": "Normal", "pvp": "PvP", "rp": "Roleplay", "hardcore": "Hardcore", "unknown": "Unknown ruleset"}


def namespace_key(info: NamespaceInfo) -> tuple[str, str]:
    region = None
    if info.region_name and info.region_name.lower() in KNOWN_REGIONS:
        region = info.region_name.lower()
    elif info.region_id in REGION_BY_ID:
        region = REGION_BY_ID[info.region_id]
    return region or "unknown", info.ruleset


def get_or_create_namespace(db: Session, info: NamespaceInfo) -> Namespace:
    region, ruleset = namespace_key(info)
    ns = db.scalar(select(Namespace).where(Namespace.game == "forever", Namespace.region == region, Namespace.ruleset == ruleset))
    if ns is None:
        ns = Namespace(
            slug=f"{region}-{ruleset}",
            game="forever",
            region=region,
            ruleset=ruleset,
            display_name=f"{region.upper() if region != 'unknown' else 'Unknown region'} · {RULESET_LABELS[ruleset]}",
        )
        db.add(ns)
        db.flush()
    return ns
