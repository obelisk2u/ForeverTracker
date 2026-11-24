"""pytest entry point for the Lua addon tests."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import REPO, lua_test_files, new_runtime, run_test_file  # noqa: E402


@pytest.mark.parametrize("lua_file", lua_test_files(), ids=lambda p: p.stem)
def test_lua_suite(lua_file):
    results = run_test_file(lua_file)
    assert results, f"{lua_file.name} defined no tests"
    failures = [f"{r['name']}\n{r['err']}" for r in results if not r["ok"]]
    assert not failures, "\n\n".join(failures)


def test_final_bosses_match_the_website():
    """The records window and the website must agree on which boss kill finishes a dungeon."""
    lua = new_runtime()
    lua.execute("Mock.loadAddon(nil)")
    table = lua.eval("Mock.ft.FINAL_ENCOUNTERS")
    in_addon = {int(map_id): {int(e) for e in finals.keys()} for map_id, finals in table.items()}
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    on_website = {int(map_id): {int(e) for e in d["final"]} for map_id, d in catalog["dungeons"].items()}
    assert in_addon == on_website


CATALOG = REPO / "backend" / "app" / "reconciliation" / "final_encounters.json"
# Forever's nine new dungeons, by instance map ID (the client's Map table; DBM-Party-Forever's TOC lists the same nine).
FOREVER_DUNGEONS = {3065, 2999, 2998, 2959, 2970, 3039, 2994, 2974, 3001}


def test_every_new_forever_dungeon_is_verified_or_pending():
    """A new Forever dungeon's final boss is listed only with live evidence; otherwise it waits, with what would settle it."""
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    listed = {int(k): v for k, v in catalog["dungeons"].items()}
    pending = {int(k): v for k, v in catalog["pending"].items() if k.isdigit()}
    assert FOREVER_DUNGEONS == (FOREVER_DUNGEONS & listed.keys()) | pending.keys()
    assert not listed.keys() & pending.keys()
    for map_id in FOREVER_DUNGEONS & listed.keys():
        assert listed[map_id].get("verified_in_game") and listed[map_id].get("evidence"), map_id
    for map_id, entry in pending.items():
        assert entry["candidate_final"] and entry["evidence_needed"] and entry["why_pending"], map_id


# A live full clear of The Drowned City (forevertracker.org run sys5kuh3ky), encounters only.
TRACE = json.loads((REPO / "fixtures" / "events" / "forever-drowned-city-full-clear.json").read_text(encoding="utf-8"))


def _replay(lua, trace, *, stop_before=None, setup=""):
    """Enter the trace's dungeon and fire each ENCOUNTER_START/END at its recorded time. Returns the time of the last event.
    `setup` is Lua run once the addon is loaded, before anything happens."""
    inst = trace["instance"]
    diff = inst["difficulty_id"] or 0
    lua.execute("boot()")
    if setup:
        lua.execute(setup)
    lua.execute(f"Mock.enterDungeon({{ name = [[{inst['name']}]], mapId = {inst['map_id']}, difficultyId = {diff} }})")
    clock = 0
    for e in trace["encounters"]:
        if e["encounter_id"] == stop_before:
            break
        eid, name = e["encounter_id"], e["name"]
        lua.execute(f"Mock.advance({e['start'] - clock}); Mock.fire('ENCOUNTER_START', {eid}, [[{name}]], {diff}, 5)")
        success = 1 if e["success"] else 0
        lua.execute(f"Mock.advance({e['end'] - e['start']}); Mock.fire('ENCOUNTER_END', {eid}, [[{name}]], {diff}, 5, {success}, {{}})")
        clock = e["end"]
    return clock


def _left_after(lua, seconds):
    lua.execute(f"Mock.advance({seconds}); Mock.leaveInstance(); Mock.advance(901)")


def test_the_live_drowned_city_clear_was_left_only_because_its_final_boss_was_missing():
    """The recorded trace, replayed through the addon as it was: leaving 55 seconds after the last kill made it 'left'."""
    lua = new_runtime()
    end = _replay(lua, TRACE, setup="Mock.ft.FINAL_ENCOUNTERS[2970] = nil")  # the catalog before this fix
    _left_after(lua, TRACE["duration_seconds"] - end)
    run = lua.eval("lastObservation('dungeon_run')")
    assert run.state == TRACE["stored_outcome"][0] == "left"
    assert len(run.encounters) == 6


def test_a_live_drowned_city_full_clear_completes_at_its_final_boss():
    lua = new_runtime()
    end = _replay(lua, TRACE)
    assert lua.eval("activeRun()") is not None, "the meter gets time to read the last fight"
    lua.execute("Mock.advance(21)")
    assert lua.eval("activeRun()") is None
    run = lua.eval("lastObservation('dungeon_run')")
    assert run.state == "unknown" and run.completion.status == "none", "a kill is not a completion event"
    assert run.instance.map_id == 2970
    assert [run.encounters[i].encounter_id for i in range(1, 7)] == [e["encounter_id"] for e in TRACE["encounters"]]
    assert run.timing.ended_at - run.encounters[6].ended_at == 20
    summary = lua.eval("ForeverTrackerDB.records.history[1]")
    assert summary.result == "completed" and summary.final_boss is True
    # Leaving afterwards does not make it a second run or change it.
    _left_after(lua, TRACE["duration_seconds"] - end)
    assert lua.eval("#observationsOf('dungeon_run')") == 1


def test_leaving_the_drowned_city_before_its_final_boss_stays_left():
    lua = new_runtime()
    _replay(lua, TRACE, stop_before=3479)
    _left_after(lua, 30)
    run = lua.eval("lastObservation('dungeon_run')")
    assert run.state == "left"
    assert len(run.encounters) == 5
    assert lua.eval("ForeverTrackerDB.records.history[1]").result == "left"
