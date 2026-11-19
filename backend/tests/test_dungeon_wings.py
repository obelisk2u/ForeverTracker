"""Scarlet Monastery's wings share instance map 189: each wing is its own dungeon, from the bosses pulled."""

from sqlalchemy import select

from app.models import Dungeon, DungeonRun
from app.services.moderation import rebuild_all
from tests.factories import T0, RunSpec, batch, run_observation
from tests.helpers import ingest, runs

GRAVEYARD = [(444, 120, True), (2779, 400, True)]
LIBRARY = [(446, 200, True), (447, 700, True)]
ARMORY = [(448, 600, True)]
CATHEDRAL = [(449, 900, True), (450, 1500, True)]


def sm(obs_id: str, start: int, encounters, **kw) -> dict:
    spec = RunSpec(
        obs_id, observer="u1", map_id=189, name="Scarlet Monastery", verified=False,
        start=start, duration=1500, encounters=encounters, **{"state": "left", **kw},
    )
    return run_observation(spec)


def dungeon_of(db, run: DungeonRun) -> Dungeon:
    return db.get(Dungeon, run.dungeon_id)


def test_each_wing_is_its_own_dungeon(db, settings):
    # One group clears the four wings back to back, then pops into the Graveyard and leaves before a boss.
    wings = [GRAVEYARD, LIBRARY, ARMORY, CATHEDRAL, []]
    observations = [sm(f"r-{i}", T0 + i * 1800, enc) for i, enc in enumerate(wings)]
    ingest(db, settings, batch("install-aaaa1111", observations))
    found = [(dungeon_of(db, r).name, dungeon_of(db, r).slug, r.outcome) for r in sorted(runs(db), key=lambda r: r.started_at)]
    assert found == [
        ("Scarlet Monastery: Graveyard", "scarlet-monastery-graveyard", "completed"),
        ("Scarlet Monastery: Library", "scarlet-monastery-library", "completed"),
        ("Scarlet Monastery: Armory", "scarlet-monastery-armory", "completed"),
        ("Scarlet Monastery: Cathedral", "scarlet-monastery-cathedral", "completed"),
        ("Scarlet Monastery", "scarlet-monastery", "left"),
    ]
    library = db.scalar(select(Dungeon).where(Dungeon.slug == "scarlet-monastery-library"))
    assert sorted(e["encounter_id"] for e in library.encounters) == [446, 447]


def test_a_run_moves_to_its_wing_once_a_boss_is_pulled(db, settings):
    # A /reload before the first boss uploads the run in progress; the next revision has the bosses.
    ingest(db, settings, batch("install-aaaa1111", [sm("r-1", T0, [], state="in_progress")]))
    (run,) = runs(db)
    assert dungeon_of(db, run).name == "Scarlet Monastery"
    public_id = run.public_id
    ingest(db, settings, batch("install-aaaa1111", [sm("r-1", T0, LIBRARY, revision=2)]))
    (run,) = runs(db)
    assert run.public_id == public_id  # same run, same URL
    assert dungeon_of(db, run).name == "Scarlet Monastery: Library"


def test_an_observer_who_saw_no_boss_joins_the_wing_run(db, settings):
    ingest(db, settings, batch("install-aaaa1111", [sm("r-1", T0, CATHEDRAL)]))
    other = run_observation(
        RunSpec("o-1", observer="u2", map_id=189, name="Scarlet Monastery", state="left", verified=False, start=T0, duration=1500, encounters=[])
    )
    ingest(db, settings, batch("install-bbbb2222", [other]))
    (run,) = runs(db)
    assert run.observation_count == 2
    assert dungeon_of(db, run).name == "Scarlet Monastery: Cathedral"


def test_runs_in_different_wings_are_never_merged(db, settings):
    ingest(db, settings, batch("install-aaaa1111", [sm("r-1", T0, GRAVEYARD)]))
    other = run_observation(
        RunSpec("o-1", observer="u2", map_id=189, name="Scarlet Monastery", state="left", verified=False, start=T0, duration=1500, encounters=LIBRARY)
    )
    ingest(db, settings, batch("install-bbbb2222", [other]))
    assert sorted(dungeon_of(db, r).name for r in runs(db)) == ["Scarlet Monastery: Graveyard", "Scarlet Monastery: Library"]


def test_a_rebuild_moves_runs_stored_before_wings_into_them(db, settings):
    ingest(db, settings, batch("install-aaaa1111", [sm("r-1", T0, ARMORY)]))
    (run,) = runs(db)
    whole = db.scalar(select(Dungeon).where(Dungeon.map_id == 189, Dungeon.wing == ""))
    # As stored before wings: in the whole dungeon, which had learned every wing's bosses.
    run.dungeon_id = whole.id
    whole.encounters = [{"encounter_id": 448, "name": "Herod"}, {"encounter_id": 444, "name": "Interrogator Vishas"}]
    db.flush()
    rebuild_all(db, settings)
    (run,) = runs(db)
    assert dungeon_of(db, run).name == "Scarlet Monastery: Armory"
    assert whole.encounters == []
