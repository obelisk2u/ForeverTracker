"""Time windows and presence intervals of a dungeon_run observation.

Matching observations into runs lives in :mod:`app.reconciliation.cluster`; consolidation of a run's
observations in :mod:`app.reconciliation.consolidate`. Both read presence through these helpers.
"""

from __future__ import annotations

from datetime import datetime

from app.models.base import from_epoch
from app.schemas.observations import DungeonRunObservation


def observation_window(obs: DungeonRunObservation) -> tuple[datetime, datetime]:
    end = obs.timing.ended_at if obs.timing.ended_at is not None else obs.timing.last_updated_at
    return from_epoch(obs.timing.started_at), from_epoch(end)


def member_intervals(obs: DungeonRunObservation, ref: str) -> list[tuple[datetime, datetime]]:
    """When roster entry ``ref`` was in the group, inside the instance. An open interval ends with the
    observation; a member without usable intervals counts as present for the whole observation."""
    _, window_end = observation_window(obs)
    for member in obs.roster:
        if member.ref == ref:
            out = []
            for p in member.presence:
                start = from_epoch(p.start)
                end = from_epoch(p.end) if p.end is not None else window_end
                if end > start:
                    out.append((start, end))
            if not out:
                out.append(observation_window(obs))
            return out
    return []
