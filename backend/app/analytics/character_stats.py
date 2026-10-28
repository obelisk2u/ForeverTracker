"""Per-character aggregates.

Each statistic is returned as a :class:`Stat` that states its value, its sample size, how
many runs were excluded and why, and the definition it implements. Missing data is never
treated as zero: a run whose death coverage is incomplete is *excluded* from "deaths per
run", not counted as a death-free run.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.analytics.definitions import MIN_PRESENCE_RATIO, STATS_DEFINITIONS_VERSION
from app.config import Settings
from app.models import (
    Character,
    CharacterStats,
    Dungeon,
    DungeonRun,
    ParticipantMetric,
    RunEncounter,
    RunParticipant,
)
from app.models.base import utcnow

COMPLETION_PRESENCE_GRACE = timedelta(minutes=2)


@dataclass
class Stat:
    definition: str
    value: float | None
    sample_size: int
    excluded: int = 0
    exclusion_reasons: dict[str, int] = field(default_factory=dict)
    note: str | None = None


@dataclass
class RunFacts:
    run: DungeonRun
    participant: RunParticipant
    dungeon: Dungeon
    metrics: dict[str, ParticipantMetric]
    boss_kills: int


def _metric_eligible(facts: RunFacts, metric: str) -> tuple[bool, str | None]:
    m = facts.metrics.get(metric)
    if m is None or m.value is None:
        return False, "metric_unavailable"
    if m.status != "observed" or m.coverage != "complete_session":
        return False, "incomplete_coverage"
    if (facts.participant.presence_ratio or 0) < MIN_PRESENCE_RATIO:
        return False, "partial_presence"
    if facts.run.outcome == "in_progress":
        return False, "run_in_progress"
    return True, None


def _collect(values: list[tuple[bool, str | None, float | None]]) -> tuple[list[float], int, dict[str, int]]:
    eligible: list[float] = []
    reasons: dict[str, int] = defaultdict(int)
    for ok, reason, value in values:
        if ok and value is not None:
            eligible.append(value)
        else:
            reasons[reason or "ineligible"] += 1
    return eligible, sum(reasons.values()), dict(reasons)


def _metric_stat(facts: list[RunFacts], metric: str, definition: str, agg: str, min_sample: int) -> Stat:
    rows = []
    for f in facts:
        ok, reason = _metric_eligible(f, metric)
        rows.append((ok, reason, f.metrics[metric].value if ok else None))
    values, excluded, reasons = _collect(rows)
    if len(values) < min_sample:
        return Stat(definition, None, len(values), excluded, reasons, note="insufficient_sample")
    value = statistics.median(values) if agg == "median" else statistics.fmean(values)
    return Stat(definition, round(value, 4), len(values), excluded, reasons)


def is_confirmed_completion(f: RunFacts) -> bool:
    run, p = f.run, f.participant
    if run.outcome != "completed" or run.completion_confidence != "verified" or run.ended_at is None:
        return False
    return p.left_at is not None and p.left_at >= run.ended_at - COMPLETION_PRESENCE_GRACE


def load_run_facts(db: Session, character_id: int) -> list[RunFacts]:
    rows = db.execute(
        select(RunParticipant, DungeonRun, Dungeon)
        .join(DungeonRun, DungeonRun.id == RunParticipant.run_id)
        .join(Dungeon, Dungeon.id == DungeonRun.dungeon_id)
        .where(
            RunParticipant.character_id == character_id,
            DungeonRun.quarantined.is_(False),
            DungeonRun.merged_into_id.is_(None),
        )
        .order_by(DungeonRun.started_at)
    ).all()
    run_ids = [r.DungeonRun.id for r in rows]
    metrics: dict[int, dict[str, ParticipantMetric]] = defaultdict(dict)
    kills: dict[int, int] = defaultdict(int)
    if run_ids:
        for m in db.scalars(
            select(ParticipantMetric).where(
                ParticipantMetric.character_id == character_id, ParticipantMetric.run_id.in_(run_ids)
            )
        ):
            metrics[m.run_id][m.metric] = m
        for enc in db.scalars(select(RunEncounter).where(RunEncounter.run_id.in_(run_ids), RunEncounter.success.is_(True))):
            kills[enc.run_id] += 1
    return [
        RunFacts(run=r.DungeonRun, participant=r.RunParticipant, dungeon=r.Dungeon, metrics=metrics[r.DungeonRun.id], boss_kills=kills[r.DungeonRun.id])
        for r in rows
    ]


def compute_stats(facts: list[RunFacts], settings: Settings) -> dict:
    n = settings.stats_min_sample
    out: dict = {"definitions_version": STATS_DEFINITIONS_VERSION}
    out["runs_observed"] = Stat("runs_observed.v1", float(len(facts)), len(facts))
    confirmed = [f for f in facts if is_confirmed_completion(f)]
    out["completions_confirmed"] = Stat("completions_confirmed.v1", float(len(confirmed)), len(facts))

    death_rows = [(*_metric_eligible(f, "deaths"), f.metrics["deaths"].value if "deaths" in f.metrics else None) for f in facts]
    death_rows = [(ok, reason, value if ok else None) for ok, reason, value in death_rows]
    deaths, excluded, reasons = _collect(death_rows)
    if len(deaths) >= n:
        out["deaths_per_run_mean"] = Stat("deaths_per_run_mean.v1", round(statistics.fmean(deaths), 4), len(deaths), excluded, reasons)
        out["deaths_per_run_median"] = Stat("deaths_per_run_median.v1", float(statistics.median(deaths)), len(deaths), excluded, reasons)
        out["death_free_run_pct"] = Stat(
            "death_free_run_pct.v1", round(100.0 * sum(1 for d in deaths if d == 0) / len(deaths), 2), len(deaths), excluded, reasons
        )
    else:
        for key in ("deaths_per_run_mean", "deaths_per_run_median", "death_free_run_pct"):
            out[key] = Stat(f"{key}.v1", None, len(deaths), excluded, reasons, note="insufficient_sample")
    # A lower bound: every death any observer saw, whatever the coverage.
    lower = sum(int(f.metrics["deaths"].value) for f in facts if "deaths" in f.metrics and f.metrics["deaths"].value is not None)
    out["deaths_observed_total"] = Stat(
        "deaths_observed_total.v1", float(lower), sum(1 for f in facts if "deaths" in f.metrics),
        note="lower_bound: includes partially observed runs",
    )

    out["dps_median"] = _metric_stat([f for f in facts if f.participant.role != "HEALER"], "dps", "dps_median.v1", "median", n)
    out["hps_median"] = _metric_stat([f for f in facts if f.participant.role == "HEALER"], "hps", "hps_median.v1", "median", n)
    out["interrupts_per_run_mean"] = _metric_stat(facts, "interrupts", "interrupts_per_run_mean.v1", "mean", n)

    durations = [float(f.run.duration_seconds) for f in confirmed if f.run.duration_seconds and (f.participant.presence_ratio or 0) >= MIN_PRESENCE_RATIO]
    out["completed_run_duration_mean"] = (
        Stat("completed_run_duration_mean.v1", round(statistics.fmean(durations), 1), len(durations), len(facts) - len(durations))
        if len(durations) >= n
        else Stat("completed_run_duration_mean.v1", None, len(durations), len(facts) - len(durations), note="insufficient_sample")
    )
    out["boss_kills_observed"] = Stat("boss_kills_observed.v1", float(sum(f.boss_kills for f in facts)), len(facts))

    by_dungeon: dict[int, list[RunFacts]] = defaultdict(list)
    for f in facts:
        by_dungeon[f.dungeon.id].append(f)
    out["by_dungeon"] = [
        {
            "dungeon": {"slug": fs[0].dungeon.slug, "name": fs[0].dungeon.name},
            "runs": len(fs),
            "completions_confirmed": sum(1 for f in fs if is_confirmed_completion(f)),
            "deaths_per_run_mean": asdict(_metric_stat(fs, "deaths", "deaths_per_run_mean.v1", "mean", n)),
            "dps_median": asdict(_metric_stat([f for f in fs if f.participant.role != "HEALER"], "dps", "dps_median.v1", "median", n)),
            "last_run_at": max(f.run.started_at for f in fs).isoformat(),
        }
        for fs in sorted(by_dungeon.values(), key=lambda fs: -len(fs))
    ]
    roles: dict[str, int] = defaultdict(int)
    for f in facts:
        roles[f.participant.role or "UNKNOWN"] += 1
    out["runs_by_role"] = dict(roles)
    out["data_quality"] = {
        "runs_with_complete_death_coverage": sum(1 for ok, _, _ in death_rows if ok),
        "runs_with_complete_meter_coverage": sum(1 for f in facts if _metric_eligible(f, "damage_done")[0]),
        "runs_reconciled_from_multiple_observers": sum(1 for f in facts if f.run.contributor_count > 1),
        "runs_in_progress_or_unknown": sum(1 for f in facts if f.run.outcome in ("in_progress", "unknown")),
    }
    return {k: (asdict(v) if isinstance(v, Stat) else v) for k, v in out.items()}


def load_run_facts_many(db: Session, character_ids: list[int]) -> dict[int, list[RunFacts]]:
    """Run facts for many characters in three queries (used after every ingested batch)."""
    out: dict[int, list[RunFacts]] = {cid: [] for cid in character_ids}
    if not character_ids:
        return out
    rows = db.execute(
        select(RunParticipant, DungeonRun, Dungeon)
        .join(DungeonRun, DungeonRun.id == RunParticipant.run_id)
        .join(Dungeon, Dungeon.id == DungeonRun.dungeon_id)
        .where(
            RunParticipant.character_id.in_(character_ids),
            DungeonRun.quarantined.is_(False),
            DungeonRun.merged_into_id.is_(None),
        )
        .order_by(DungeonRun.started_at)
    ).all()
    run_ids = sorted({r.DungeonRun.id for r in rows})
    metrics: dict[tuple[int, int], dict[str, ParticipantMetric]] = defaultdict(dict)
    kills: dict[int, int] = defaultdict(int)
    if run_ids:
        for m in db.scalars(
            select(ParticipantMetric).where(
                ParticipantMetric.character_id.in_(character_ids), ParticipantMetric.run_id.in_(run_ids)
            )
        ):
            metrics[(m.character_id, m.run_id)][m.metric] = m
        for run_id, n in db.execute(
            select(RunEncounter.run_id, func.count())
            .where(RunEncounter.run_id.in_(run_ids), RunEncounter.success.is_(True))
            .group_by(RunEncounter.run_id)
        ):
            kills[run_id] = n
    for r in rows:
        p, run = r.RunParticipant, r.DungeonRun
        out[p.character_id].append(
            RunFacts(run=run, participant=p, dungeon=r.Dungeon, metrics=metrics[(p.character_id, run.id)], boss_kills=kills[run.id])
        )
    return out


def recompute_many(db: Session, character_ids: set[int] | list[int], settings: Settings) -> None:
    ids = sorted(character_ids)
    if not ids:
        return
    db.flush()
    for start in range(0, len(ids), 500):
        chunk = ids[start : start + 500]
        facts = load_run_facts_many(db, chunk)
        now = utcnow()
        rows = []
        for cid in chunk:
            fs = facts[cid]
            stats = compute_stats(fs, settings)
            rows.append(
                {
                    "character_id": cid,
                    "definitions_version": STATS_DEFINITIONS_VERSION,
                    "computed_at": now,
                    "runs_observed": len(fs),
                    "completions_confirmed": int(stats["completions_confirmed"]["value"]),
                    "last_run_at": max((f.run.started_at for f in fs), default=None),
                    "stats": stats,
                }
            )
        stmt = pg_insert(CharacterStats).values(rows)
        db.execute(
            stmt.on_conflict_do_update(
                index_elements=[CharacterStats.character_id],
                set_={k: stmt.excluded[k] for k in rows[0] if k != "character_id"},
            )
        )
    # The upsert bypassed the ORM: drop any cached CharacterStats rows so reads see new values.
    for obj in list(db.identity_map.values()):
        if isinstance(obj, CharacterStats):
            db.expire(obj)


def recompute_character_stats(db: Session, character_id: int, settings: Settings) -> None:
    if db.get(Character, character_id) is not None:
        recompute_many(db, [character_id], settings)


def trend_buckets(facts: list[RunFacts]) -> list[dict]:
    """Weekly series of eligible per-run values. Buckets without eligible runs carry no value."""
    if not facts:
        return []
    buckets: dict[datetime, list[RunFacts]] = defaultdict(list)
    for f in facts:
        start = f.run.started_at
        key = (start - timedelta(days=start.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        buckets[key].append(f)
    series = []
    for key in sorted(buckets):
        fs = buckets[key]
        deaths = _metric_stat(fs, "deaths", "deaths_per_run_mean.v1", "mean", 1)
        dps = _metric_stat([f for f in fs if f.participant.role != "HEALER"], "dps", "dps_median.v1", "median", 1)
        interrupts = _metric_stat(fs, "interrupts", "interrupts_per_run_mean.v1", "mean", 1)
        series.append(
            {
                "period_start": key.isoformat(),
                "runs": len(fs),
                "deaths_per_run": {"value": deaths.value, "sample_size": deaths.sample_size},
                "dps_median": {"value": dps.value, "sample_size": dps.sample_size},
                "interrupts_per_run": {"value": interrupts.value, "sample_size": interrupts.sample_size},
            }
        )
    return series
