"""End-to-end: the real addon (in a Lua 5.1 VM, mocked client) -> SavedVariables file ->
website upload endpoint -> ingestion -> reconciliation -> public API.

This proves the pipeline works on simulated client behaviour. It does NOT prove the real
Forever client behaves like the mock (see docs/FOREVER_LAUNCH_VALIDATION.md).

Set FT_WRITE_FRONTEND_FIXTURES=1 to export the API responses for the frontend tests.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "addon" / "tests"))

from harness import new_runtime, savedvariables_text  # noqa: E402

pytestmark = pytest.mark.e2e

FIXTURE_DIR = REPO / "frontend" / "tests" / "fixtures" / "e2e"

# The dungeon, as every party member's client experiences it. Times are seconds after login.
SCENARIO = """
local observerIndex, entryDelay, tankDamageFactor = ...
local party = DefaultParty()
local me = table.remove(party, observerIndex)
table.insert(party, 1, me)
boot(party)
Mock.advance(entryDelay)
Mock.enterDungeon({ name = "Hall of Thanes", mapId = 990001 })
Mock.advance(60 - entryDelay)

local function fight(duration, values)
  Mock.startCombat()
  Mock.advance(duration)
  Mock.endCombat(duration, values)
  Mock.advance(15)
end

-- Trash pull.
fight(40, {
  Autumn = { damage_done = 30000, interrupts = 1 }, Mah = { damage_done = 18000 * tankDamageFactor },
  Phineas = { healing_done = 21000, dispels = 1 }, Asha = { damage_done = 26000, interrupts = 1 },
  Thalen = { damage_done = 24000 },
})
Mock.advance(120)
-- First boss: the tank dies once and is resurrected after the kill.
Mock.fire("ENCOUNTER_START", 3001, "Thane Ironvow", 1, 5)
Mock.startCombat()
Mock.advance(50)
Mock.setDead("Mah", true)
Mock.advance(40)
Mock.endCombat(90, {
  Autumn = { damage_done = 70000 }, Mah = { damage_done = 30000 * tankDamageFactor, deaths = 1 },
  Phineas = { healing_done = 52000 }, Asha = { damage_done = 61000, interrupts = 2 }, Thalen = { damage_done = 58000 },
})
Mock.fire("ENCOUNTER_END", 3001, "Thane Ironvow", 1, 5, 1, {})
Mock.advance(30)
Mock.setDead("Mah", false)
Mock.advance(200)
-- Final boss.
Mock.fire("ENCOUNTER_START", 3002, "The Hollow King", 1, 5)
fight(120, {
  Autumn = { damage_done = 95000, interrupts = 2 }, Mah = { damage_done = 41000 * tankDamageFactor },
  Phineas = { healing_done = 80000 }, Asha = { damage_done = 88000 }, Thalen = { damage_done = 90000 },
})
Mock.fire("ENCOUNTER_END", 3002, "The Hollow King", 1, 5, 1, {})
Mock.fire("LFG_COMPLETION_REWARD")
Mock.advance(45)
Mock.leaveInstance()
Mock.advance(5)
Mock.saveVariables() -- logging out writes ForeverTracker.lua
"""


def play(observer_index: int, entry_delay: int, tank_damage_factor: float = 1.0) -> str:
    lua = new_runtime(seed=1000 + observer_index)  # each player's client is a separate installation
    lua.execute(SCENARIO, observer_index, entry_delay, tank_damage_factor)
    return savedvariables_text(lua)


def upload(client, text: str) -> dict:
    res = client.post(
        "/api/v1/ingest/savedvariables",
        files={"file": ("ForeverTracker.lua", text.encode("utf-8"), "text/plain")},
    )
    assert res.status_code == 200, res.text
    return res.json()


def history(client, character_id: str) -> dict:
    return client.get(f"/api/v1/characters/us-pve/{character_id}/runs").json()


def test_two_observers_one_run_full_pipeline(client):
    # 1. One addon user (Autumn) completes a dungeon with four others.
    sv_autumn = play(observer_index=1, entry_delay=0)
    assert 'ForeverTrackerDB = {' in sv_autumn and '["installation_id"]' in sv_autumn

    # 2. The SavedVariables file is uploaded.
    first = upload(client, sv_autumn)
    assert first["summary"]["dungeon_runs"] == 1
    statuses = {o["type"]: o["status"] for b in first["batches"] for o in b["observations"]}
    assert statuses == {"dungeon_run": "accepted", "character_snapshot": "accepted"}, first

    # 3. Five character records exist.
    party = ["Autumn Redleaf", "Mah Beardlong", "Phineas Longhorn", "Asha Brightvale", "Thalen Brightvale"]
    by_name = {}
    for name in party:
        found = client.get("/api/v1/search", params={"q": name, "exact": "true"}).json()
        assert found["total"] == 1, (name, found)
        by_name[name] = found["results"][0]
    assert all(by_name[n]["identity_confidence"] == "guid_confirmed" for n in party)
    assert by_name["Mah Beardlong"]["namespace"] == "us-pve"

    # 4. The dungeon appears in every character's history, including those without the addon.
    run_ids = set()
    for name in party:
        h = history(client, by_name[name]["id"])
        assert h["total"] == 1, name
        run_ids.add(h["items"][0]["run_id"])
    (run_id,) = run_ids
    run = client.get(f"/api/v1/runs/{run_id}").json()
    assert run["dungeon"]["name"] == "Hall of Thanes"
    assert run["outcome"] == "completed" and run["completion_confidence"] == "verified"
    assert [e["name"] for e in run["encounters"]] == ["Thane Ironvow", "The Hollow King"]
    assert all(e["success"] for e in run["encounters"])
    tank = next(p for p in run["participants"] if p["character"]["full_name"] == "Mah Beardlong")
    assert tank["metrics"]["damage_done"]["value"] == 89000
    assert tank["metrics"]["damage_done"]["source"] == "native_damage_meter"
    assert tank["metrics"]["damage_done"]["coverage"] == "complete_session"
    assert tank["metrics"]["deaths"]["value"] == 1
    mage = next(p for p in run["participants"] if p["character"]["full_name"] == "Autumn Redleaf")
    assert mage["metrics"]["interrupts"]["value"] == 3
    assert round(mage["metrics"]["dps"]["value"], 3) == round(195000 / 250, 3)
    assert len(run["deaths"]) == 1 and run["deaths"][0]["sources"] == ["unit_state"]
    assert run["match_status"] == "single"

    # 5. A second observer (Phineas, the healer, zoned in 20 s later) uploads the same run.
    #    Their meter showed the tank's damage 5% lower: a genuine conflict to preserve.
    sv_phineas = play(observer_index=3, entry_delay=20, tank_damage_factor=0.95)
    upload(client, sv_phineas)

    # 6. Reconciled, not duplicated.
    for name in party:
        assert history(client, by_name[name]["id"])["total"] == 1, name
    run = client.get(f"/api/v1/runs/{run_id}").json()
    assert run["observation_count"] == 2 and run["contributor_count"] == 2
    assert run["match_status"] == "reconciled"
    assert len(run["encounters"]) == 2 and all(e["observed_by"] == 2 for e in run["encounters"])
    assert len(run["deaths"]) == 1 and run["deaths"][0]["observed_by"] == 2  # one death, seen twice
    assert {s["observer"] for s in run["sources"]} == {"Observer A", "Observer B"}

    # 7. Agreeing metrics are corroborated; the conflicting one keeps every candidate.
    by = {p["character"]["full_name"]: p for p in run["participants"]}
    assert by["Autumn Redleaf"]["metrics"]["damage_done"]["resolution"] == "corroborated"
    tank = by["Mah Beardlong"]
    assert tank["metrics"]["damage_done"]["resolution"] == "conflicted"
    values = sorted(c["value"] for c in tank["candidates"]["damage_done"])
    assert values == [84550.0, 89000.0]
    assert tank["conflicts"]["damage_done"]["reason"] == "observers_disagree"
    assert tank["metrics"]["deaths"]["resolution"] == "corroborated"

    # Re-uploading the first file changes nothing.
    again = upload(client, sv_autumn)
    assert all(b["duplicate_batch"] for b in again["batches"])
    assert client.get(f"/api/v1/runs/{run_id}").json()["observation_count"] == 2

    # 8. Aggregates reflect the reconciled run.
    tank_profile = client.get(f"/api/v1/characters/us-pve/{by_name['Mah Beardlong']['id']}").json()
    stats = tank_profile["stats"]
    assert stats["runs_observed"]["value"] == 1
    assert stats["completions_confirmed"]["value"] == 1
    assert stats["deaths_per_run_mean"]["value"] == 1.0 and stats["deaths_per_run_mean"]["sample_size"] == 1
    assert stats["death_free_run_pct"]["value"] == 0.0
    asha = client.get(f"/api/v1/characters/us-pve/{by_name['Asha Brightvale']['id']}").json()
    assert asha["stats"]["death_free_run_pct"]["value"] == 100.0
    assert asha["latest_gear"] is not None and asha["latest_gear"]["source"] == "inspect"
    companions = client.get(f"/api/v1/characters/us-pve/{by_name['Asha Brightvale']['id']}/companions").json()
    assert {c["character"]["full_name"] for c in companions} == set(party) - {"Asha Brightvale"}

    if os.environ.get("FT_WRITE_FRONTEND_FIXTURES"):
        FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
        cid = by_name["Mah Beardlong"]["id"]
        dumps = {
            "run.json": run,
            "profile.json": tank_profile,
            "history.json": history(client, cid),
            "search.json": client.get("/api/v1/search", params={"q": "bright"}).json(),
        }
        for name, payload in dumps.items():
            (FIXTURE_DIR / name).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def test_export_string_from_the_addon_is_accepted(client):
    """The /ft export string (JSON) goes through the same pipeline as the file."""
    lua = new_runtime()
    lua.execute(
        """
        boot()
        Mock.enterDungeon({ name = "Ruins of Lordaeron", mapId = 990002 })
        Mock.startCombat()
        Mock.advance(30)
        Mock.endCombat(30, { Autumn = { damage_done = 1000 } })
        Mock.advance(15)
        """
    )
    text = lua.eval("Mock.ft.Export.string(true)")
    res = client.post("/api/v1/ingest/export", content=text, headers={"Content-Type": "application/json"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["summary"]["in_progress_runs"] == 1
    run_id = next(o["run_id"] for b in body["batches"] for o in b["observations"] if o["type"] == "dungeon_run")
    run = client.get(f"/api/v1/runs/{run_id}").json()
    assert run["outcome"] == "in_progress"
