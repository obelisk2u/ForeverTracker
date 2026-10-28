from datetime import UTC, datetime, timedelta

import pytest

from app.analytics.character_stats import load_run_facts, compute_stats
from app.analytics.wipes import DeathPoint, EncounterPoint, Presence, detect_wipes
from app.reconciliation.metrics import Candidate, resolve
from tests.factories import T0, RunSpec, batch, run_observation
from tests.helpers import character, ingest

NOW = datetime(2026, 10, 20, tzinfo=UTC)


def cand(value, *, contributor=1, coverage="complete_session", status="observed", source="native_damage_meter", metric="deaths", ratio=1.0):
    return Candidate(
        character_id=1, metric=metric, value=value, source=source, status=status, coverage=coverage, coverage_ratio=ratio,
        combat_seconds=600.0, contributor_ids=frozenset({contributor}), raw_observation_id=contributor, collected_at=NOW,
    )


class TestResolution:
    def test_agreeing_contributors_corroborate(self):
        r = resolve([cand(2, contributor=1), cand(2, contributor=2)], 0.01)
        assert (r.value, r.resolution, r.confidence, r.contributor_count) == (2, "corroborated", "high", 2)

    def test_amounts_within_tolerance_agree(self):
        r = resolve([cand(100_000, metric="damage_done"), cand(100_500, contributor=2, metric="damage_done")], 0.01)
        assert r.resolution == "corroborated" and r.value == 100_250

    def test_disagreement_is_conflicted_and_keeps_best_coverage(self):
        r = resolve([cand(1, ratio=0.97), cand(3, contributor=2, ratio=0.99)], 0.01)
        assert r.resolution == "conflicted" and r.value == 3 and r.confidence == "low"
        assert len(r.conflict["candidates"]) == 2

    def test_complete_coverage_beats_partial(self):
        r = resolve([cand(5, coverage="partial_session", status="incomplete", ratio=0.4), cand(2, contributor=2)], 0.01)
        assert r.value == 2 and r.resolution == "single_source" and r.coverage == "complete_session"

    def test_source_priority_and_cross_source_conflict(self):
        r = resolve([cand(2), cand(1, source="death_events")], 0.01)
        assert r.source == "native_damage_meter" and r.value == 2
        assert r.resolution == "conflict_resolved" and r.conflict["reason"] == "sources_disagree"

    def test_unavailable_never_becomes_zero(self):
        r = resolve([cand(None, status="unavailable")], 0.01)
        assert r.value is None and r.status == "unavailable"


def _run(db, settings, oid, start, deaths, *, track=True, observer="u1", install="install-aaaa1111", meter_deaths=None, **kw):
    spec = RunSpec(oid, observer=observer, start=start, deaths=deaths, track_deaths=track, meter_deaths=meter_deaths, **kw)
    ingest(db, settings, batch(install, [run_observation(spec)]))


class TestCharacterStats:
    def test_death_statistics_exclude_incomplete_runs(self, db, settings):
        # Three fully covered runs: 0, 2 and 1 deaths for the tank (u2).
        _run(db, settings, "r-1", T0, {})
        _run(db, settings, "r-2", T0 + 7200, {"u2": [100, 900]})
        _run(db, settings, "r-3", T0 + 14400, {"u2": [300]})
        # A run where the meter was secret and death tracking was off: its 0 must not count as "death-free".
        _run(db, settings, "r-4", T0 + 21600, {}, track=False, meter_status="secret")
        tank = character(db, "Mah Beardlong")
        stats = compute_stats(load_run_facts(db, tank.id), settings)
        assert stats["runs_observed"]["value"] == 4
        mean = stats["deaths_per_run_mean"]
        assert mean["value"] == 1.0 and mean["sample_size"] == 3 and mean["excluded"] == 1
        assert stats["deaths_per_run_median"]["value"] == 1.0
        assert stats["death_free_run_pct"]["value"] == pytest.approx(33.33, abs=0.01)
        assert stats["data_quality"]["runs_with_complete_death_coverage"] == 3

    def test_partial_presence_excludes_run(self, db, settings):
        from tests.factories import party

        members = party()
        members[1].presence = [(T0 + 1500, T0 + 1800)]  # tank joined for the last 5 minutes
        _run(db, settings, "r-1", T0, {}, members=members)
        tank = character(db, "Mah Beardlong")
        stats = compute_stats(load_run_facts(db, tank.id), settings)
        assert stats["deaths_per_run_mean"]["value"] is None
        assert stats["deaths_per_run_mean"]["exclusion_reasons"] == {"partial_presence": 1}
        assert stats["completions_confirmed"]["value"] == 1  # present at the end, so the completion counts

    def test_sample_size_gate(self, db, settings, monkeypatch):
        monkeypatch.setattr(settings, "stats_min_sample", 3)
        _run(db, settings, "r-1", T0, {})
        _run(db, settings, "r-2", T0 + 7200, {})
        stats = compute_stats(load_run_facts(db, character(db, "Autumn Redleaf").id), settings)
        assert stats["dps_median"]["value"] is None and stats["dps_median"]["note"] == "insufficient_sample"
        assert stats["dps_median"]["sample_size"] == 2

    def test_performance_aggregation_by_role(self, db, settings):
        _run(db, settings, "r-1", T0, {})
        _run(db, settings, "r-2", T0 + 7200, {}, combat_seconds=600.0)
        mage = compute_stats(load_run_facts(db, character(db, "Autumn Redleaf").id), settings)
        # 540000 damage over 900 s and over 600 s of meter combat time -> median of 600 and 900 dps.
        assert mage["dps_median"]["value"] == pytest.approx((540000 / 900 + 540000 / 600) / 2)
        priest = compute_stats(load_run_facts(db, character(db, "Phineas Longhorn").id), settings)
        assert priest["hps_median"]["value"] == pytest.approx((400000 / 900 + 400000 / 600) / 2)
        assert priest["dps_median"]["sample_size"] == 0  # healers are not in the DPS statistic

    def test_in_progress_runs_do_not_count_as_results(self, db, settings):
        _run(db, settings, "r-1", T0, {}, state="in_progress", verified=False, duration=600, combat_seconds=300)
        stats = compute_stats(load_run_facts(db, character(db, "Mah Beardlong").id), settings)
        assert stats["completions_confirmed"]["value"] == 0
        assert stats["deaths_per_run_mean"]["exclusion_reasons"] == {"run_in_progress": 1}


class TestWipes:
    t = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)

    def presences(self, n=3):
        return [Presence(i, self.t - timedelta(hours=1), None) for i in range(n)]

    def test_party_wipe_is_inferred(self):
        deaths = [DeathPoint(0, self.t), DeathPoint(1, self.t + timedelta(seconds=5)), DeathPoint(2, self.t + timedelta(seconds=12))]
        (w,) = detect_wipes(self.presences(), deaths, [], death_coverage="complete")
        assert w.kind == "party_wipe" and w.inferred is True

    def test_partial_deaths_are_not_a_wipe(self):
        deaths = [DeathPoint(0, self.t), DeathPoint(1, self.t + timedelta(seconds=5))]
        assert detect_wipes(self.presences(), deaths, [], death_coverage="complete") == []

    def test_failed_encounter_is_reported(self):
        enc = [EncounterPoint(3001, self.t, self.t + timedelta(seconds=60), False)]
        (w,) = detect_wipes(self.presences(), [], enc, death_coverage="none")
        assert w.kind == "encounter_failed" and w.inferred is False
