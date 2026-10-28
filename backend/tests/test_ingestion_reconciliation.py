from sqlalchemy import select

from app.models import (
    Character,
    CharacterIdentityEvidence,
    DungeonRun,
    MetricObservation,
    RawObservation,
    RunDeath,
    RunEncounter,
    RunMatchCandidate,
    RunParticipant,
    UploadBatch,
)
from tests.factories import T0, Member, RunSpec, batch, party, run_observation
from tests.helpers import character, count, ingest, metric, runs


def test_one_observer_contributes_the_whole_party(db, settings):
    result = ingest(db, settings, batch("install-aaaa1111", [run_observation(RunSpec("r-1", observer="u1"))]))
    assert result.status == "processed"
    assert count(db, Character) == 5
    (run,) = runs(db)
    assert run.observation_count == 1 and run.match_status == "single"
    assert run.outcome == "completed" and run.completion_confidence == "verified"
    assert count(db, RunParticipant) == 5
    tank = character(db, "Mah Beardlong")
    assert tank.identity_confidence == "guid_confirmed"
    dmg = metric(db, run.id, tank.id, "damage_done")
    assert dmg.value == 301_000.0
    assert dmg.source == "native_damage_meter" and dmg.status == "observed" and dmg.coverage == "complete_session"
    assert dmg.resolution == "single_source"
    dps = metric(db, run.id, tank.id, "dps")
    assert dps.derived and round(dps.value, 2) == round(301_000.0 / 900.0, 2)


def test_second_observer_is_reconciled_not_duplicated(db, settings):
    ingest(db, settings, batch("install-aaaa1111", [run_observation(RunSpec("r-1", observer="u1"))]))
    # Observer 2 zoned in 40 s later and recorded slightly different session timing.
    second = RunSpec("x-77", observer="u3", start=T0 + 40, duration=1770)
    ingest(db, settings, batch("install-bbbb2222", [run_observation(second)]))

    (run,) = runs(db)
    assert run.observation_count == 2 and run.contributor_count == 2
    assert run.match_status == "reconciled"
    assert count(db, Character) == 5
    assert count(db, RunParticipant) == 5
    assert count(db, RunEncounter) == 2  # the same two boss pulls, not four
    tank = character(db, "Mah Beardlong")
    dmg = metric(db, run.id, tank.id, "damage_done")
    assert dmg.resolution == "corroborated" and dmg.contributor_count == 2
    # Both candidates are preserved with provenance.
    cands = db.scalars(
        select(MetricObservation).where(MetricObservation.character_id == tank.id, MetricObservation.metric == "damage_done")
    ).all()
    assert len(cands) == 2


def test_duplicate_upload_is_idempotent(db, settings):
    payload = batch("install-aaaa1111", [run_observation(RunSpec("r-1", observer="u1"))])
    first = ingest(db, settings, payload)
    second = ingest(db, settings, payload)
    assert second.duplicate_batch and second.upload_id == first.upload_id
    assert count(db, UploadBatch) == 1 and count(db, RawObservation) == 1 and count(db, DungeonRun) == 1

    # The same observation inside a different batch is a per-observation duplicate.
    again = batch("install-aaaa1111", [run_observation(RunSpec("r-1", observer="u1"))] * 1)
    again["batch_id"] = "test-different-batch-id"
    third = ingest(db, settings, again)
    assert third.observations[0].status == "duplicate"
    assert count(db, RawObservation) == 1 and count(db, DungeonRun) == 1


def test_conflicting_death_counts_are_preserved_not_hidden(db, settings):
    a = RunSpec("r-1", observer="u1", deaths={"u2": [400]}, meter_deaths={"u2": 1})
    # Offsets are relative to each observer's entry time; both saw the death at T0 + 400 (±1 s clock jitter).
    b = RunSpec("r-9", observer="u3", start=T0 + 30, duration=1770, deaths={"u2": [371]}, meter_deaths={"u2": 3})
    ingest(db, settings, batch("install-aaaa1111", [run_observation(a)]))
    ingest(db, settings, batch("install-bbbb2222", [run_observation(b)]))
    (run,) = runs(db)
    tank = character(db, "Mah Beardlong")
    deaths = metric(db, run.id, tank.id, "deaths")
    assert deaths.resolution == "conflicted"
    assert deaths.confidence == "low"
    assert sorted(c["value"] for c in deaths.conflict["candidates"]) == [1.0, 3.0]
    # The death itself was seen by both observers and deduplicated into one event.
    (death,) = db.scalars(select(RunDeath).where(RunDeath.character_id == tank.id)).all()
    assert death.observation_count == 2


def test_unrelated_groups_in_same_dungeon_stay_separate(db, settings):
    ingest(db, settings, batch("install-aaaa1111", [run_observation(RunSpec("r-1", observer="u1"))]))
    other_party = [
        Member("u1", "Kira", "Stonefist", "Player-4620-0000B1", "PALADIN", "Dwarf", 18, "TANK"),
        Member("u2", "Lio", "Ashgrove", "Player-4620-0000B2", "MAGE", "Human", 18, "DAMAGER"),
        Member("u3", "Nym", "Ashgrove", "Player-4620-0000B3", "PRIEST", "Human", 18, "HEALER"),
    ]
    ingest(db, settings, batch("install-cccc3333", [run_observation(RunSpec("q-1", observer="u1", members=other_party, start=T0 + 60))]))
    assert count(db, DungeonRun) == 2


def test_party_guid_mismatch_vetoes_a_match(db, settings):
    ingest(db, settings, batch("install-aaaa1111", [run_observation(RunSpec("r-1", observer="u1", party_guid="Party-1-AAA"))]))
    ingest(db, settings, batch("install-bbbb2222", [run_observation(RunSpec("r-2", observer="u2", party_guid="Party-1-BBB"))]))
    assert count(db, DungeonRun) == 2


def test_back_to_back_runs_of_same_group_are_not_merged(db, settings):
    first = RunSpec("r-1", observer="u1", duration=1500)
    second = RunSpec("r-2", observer="u1", start=T0 + 1800, duration=1500)
    ingest(db, settings, batch("install-aaaa1111", [run_observation(first), run_observation(second)]))
    assert count(db, DungeonRun) == 2


def test_guid_with_contradicting_class_is_quarantined(db, settings):
    ingest(db, settings, batch("install-aaaa1111", [run_observation(RunSpec("r-1", observer="u1"))]))
    forged = party()
    forged[1].class_file = "MAGE"  # same GUID as the warrior
    result = ingest(db, settings, batch("install-dddd4444", [run_observation(RunSpec("z-1", observer="u1", members=forged, start=T0 + 7200))]))
    assert result.observations[0].status == "quarantined"
    assert result.observations[0].reasons == ["guid_class_conflict"]
    assert count(db, DungeonRun) == 1
    assert character(db, "Mah Beardlong").class_file == "WARRIOR"


def test_new_revision_supersedes_in_progress_record(db, settings):
    live = RunSpec("r-1", observer="u1", state="in_progress", verified=False, duration=600, combat_seconds=300)
    ingest(db, settings, batch("install-aaaa1111", [run_observation(live)]))
    (run,) = runs(db)
    assert run.outcome == "in_progress"
    public_id = run.public_id
    final = RunSpec("r-1", observer="u1", revision=2)
    ingest(db, settings, batch("install-aaaa1111", [run_observation(final)]))
    (run,) = runs(db)
    assert run.public_id == public_id  # same canonical run, stable URL
    assert run.outcome == "completed"
    statuses = sorted(db.scalars(select(RawObservation.status)))
    assert statuses == ["accepted", "superseded"]

    # Re-sending revision 1 unchanged is a duplicate; different content under revision 1 is rejected.
    resend = batch("install-aaaa1111", [run_observation(live)])
    resend["batch_id"] = "test-resend-rev1"
    assert ingest(db, settings, resend).observations[0].status == "duplicate"
    forged = RunSpec("r-1", observer="u1", state="in_progress", verified=False, duration=700, combat_seconds=300)
    assert ingest(db, settings, batch("install-aaaa1111", [run_observation(forged)])).observations[0].reasons == [
        "revision_content_conflict"
    ]
    assert runs(db)[0].outcome == "completed"


def test_older_revision_arriving_late_is_stale(db, settings):
    ingest(db, settings, batch("install-aaaa1111", [run_observation(RunSpec("r-1", observer="u1", revision=3))]))
    late = RunSpec("r-1", observer="u1", revision=2, state="in_progress", verified=False, duration=600, combat_seconds=300)
    result = ingest(db, settings, batch("install-aaaa1111", [run_observation(late)]))
    assert result.observations[0].status == "stale"
    (run,) = runs(db)
    assert run.outcome == "completed"
    assert sorted(db.scalars(select(RawObservation.status))) == ["accepted", "superseded"]


def test_same_name_in_two_namespaces_are_two_characters(db, settings):
    eu = party("E")
    ingest(db, settings, batch("install-aaaa1111", [run_observation(RunSpec("r-1", observer="u1"))]))
    ingest(db, settings, batch("install-eeee5555", [run_observation(RunSpec("r-1", observer="u1", members=eu, region_id=3))]))
    assert len(db.scalars(select(Character).where(Character.full_name == "Autumn Redleaf")).all()) == 2


def test_name_only_entries_never_merge_into_ambiguous_matches(db, settings):
    # Two different GUID-confirmed characters have held the name "Asha Brightvale" in one namespace.
    a = party()
    b = party("Z")
    ingest(db, settings, batch("install-aaaa1111", [run_observation(RunSpec("r-1", observer="u1", members=a))]))
    ingest(db, settings, batch("install-ffff6666", [run_observation(RunSpec("r-2", observer="u1", members=b, start=T0 + 200 * 86400))]))
    assert len(db.scalars(select(Character).where(Character.full_name == "Asha Brightvale")).all()) == 2

    # A name-only roster entry half-way between them cannot be attributed safely.
    anon = party("Q")
    anon[3].guid = None
    ingest(db, settings, batch("install-gggg7777", [run_observation(RunSpec("r-3", observer="u1", members=anon, start=T0 + 100 * 86400))]))
    assert len(db.scalars(select(Character).where(Character.full_name == "Asha Brightvale")).all()) == 2
    run3 = runs(db)[-1]
    assert run3.coverage["roster_entries_unidentified"] == 1


def test_secret_identity_is_not_guessed(db, settings):
    members = party()
    members[4].identity_status = "secret"
    members[4].name = None
    members[4].guid = None
    ingest(db, settings, batch("install-aaaa1111", [run_observation(RunSpec("r-1", observer="u1", members=members))]))
    assert count(db, Character) == 4
    assert runs(db)[0].coverage["roster_entries_unidentified"] == 1


def test_unavailable_meter_metrics_are_not_zero(db, settings):
    spec = RunSpec("r-1", observer="u1", meter={}, meter_status="secret")
    obs = run_observation(spec)
    for totals in obs["meter"]["totals"]:
        totals["metrics"] = {"damage_done": {"value": None, "status": "secret", "sessions": 0}}
    obs["meter"]["sessions"] = [{"session_id": 1, "status": "secret"}]
    ingest(db, settings, batch("install-aaaa1111", [obs]))
    (run,) = runs(db)
    dmg = metric(db, run.id, character(db, "Mah Beardlong").id, "damage_done")
    assert dmg.value is None and dmg.status == "unavailable"
    assert metric(db, run.id, character(db, "Mah Beardlong").id, "dps") is None


def test_abandoned_and_left_runs_are_not_completions(db, settings):
    ingest(db, settings, batch("install-aaaa1111", [run_observation(RunSpec("r-1", observer="u1", state="left", verified=False))]))
    ingest(db, settings, batch("install-aaaa1111", [run_observation(RunSpec("r-2", observer="u1", state="abandoned", verified=False, start=T0 + 7200))]))
    outcomes = sorted((r.outcome, r.completion_confidence) for r in runs(db))
    assert outcomes == [("abandoned", "none"), ("left", "none")]


def test_ambiguous_match_is_recorded_not_guessed(db, settings):
    # Two runs that each share two characters with the incoming observation, equally well.
    m = party()
    group_a = [m[0], m[1], Member("u6", "Oro", "Fen", "Player-4620-0000C6", "DRUID", "NightElf", 18, "HEALER")]
    group_b = [m[2], m[3], Member("u7", "Pell", "Fen", "Player-4620-0000C7", "SHAMAN", "Dwarf", 18, "HEALER")]
    for g in (group_a, group_b):
        for x in g:
            x.presence = None
    ingest(db, settings, batch("install-aaaa1111", [run_observation(RunSpec("a-1", observer="u1", members=group_a, encounters=[]))]))
    ingest(db, settings, batch("install-bbbb2222", [run_observation(RunSpec("b-1", observer="u3", members=group_b, encounters=[]))]))
    assert count(db, DungeonRun) == 2  # disjoint groups: no shared characters
    bridge = [m[0], m[1], m[2], m[3]]
    ingest(db, settings, batch("install-cccc3333", [run_observation(RunSpec("c-1", observer="u1", members=bridge, encounters=[]))]))
    assert count(db, DungeonRun) == 3
    assert count(db, RunMatchCandidate) == 2
    assert runs(db)[-1].match_status == "unresolved"


def test_identity_evidence_records_renames(db, settings):
    ingest(db, settings, batch("install-aaaa1111", [run_observation(RunSpec("r-1", observer="u1"))]))
    renamed = party()
    renamed[0].name = "Autumne"
    ingest(db, settings, batch("install-aaaa1111", [run_observation(RunSpec("r-2", observer="u1", members=renamed, start=T0 + 86400))]))
    assert count(db, Character) == 5
    mage = db.scalar(select(Character).where(Character.class_file == "MAGE"))
    assert mage.full_name == "Autumne Redleaf"
    names = db.scalars(
        select(CharacterIdentityEvidence.display_value).where(
            CharacterIdentityEvidence.character_id == mage.id, CharacterIdentityEvidence.kind == "name"
        )
    ).all()
    assert sorted(names) == ["Autumn Redleaf", "Autumne Redleaf"]
