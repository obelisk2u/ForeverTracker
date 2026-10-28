"""Addon (Lua VM) -> SavedVariables in a WoW folder -> desktop uploader -> API."""

import os
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "addon" / "tests"))

from harness import new_runtime, savedvariables_text  # noqa: E402

pytestmark = pytest.mark.e2e


def test_uploader_syncs_addon_output_into_the_api(client, tmp_path):
    from forevertracker_uploader.client import Uploader
    from forevertracker_uploader.config import Config, State
    from forevertracker_uploader.sync import sync_once

    lua = new_runtime()
    lua.execute(
        """
        boot()
        Mock.enterDungeon({ name = "Alcaz Prison", mapId = 990007 })
        Mock.startCombat()
        Mock.advance(45)
        Mock.endCombat(45, { Autumn = { damage_done = 20000 }, Mah = { damage_done = 9000 } })
        Mock.advance(15)
        Mock.fire("LFG_COMPLETION_REWARD")
        Mock.leaveInstance()
        Mock.advance(5)
        Mock.saveVariables()
        """
    )
    sv = tmp_path / "World of Warcraft" / "_forever_" / "WTF" / "Account" / "1#1" / "SavedVariables" / "ForeverTracker.lua"
    sv.parent.mkdir(parents=True)
    sv.write_text(savedvariables_text(lua), encoding="utf-8")
    old = time.time() - 60
    os.utime(sv, (old, old))

    home = tmp_path / "uploader-home"
    cfg = Config(server_url="http://localhost", wow_paths=[str(tmp_path / "World of Warcraft")])
    state = State()
    uploader = Uploader(cfg.server_url, transport=client._transport)
    report = sync_once(home, cfg, state, uploader)
    assert report.errors == [], report.errors
    assert report.batches_uploaded == 1
    assert report.observations.get("accepted", 0) >= 2  # the run plus equipment snapshots

    found = client.get("/api/v1/search", params={"q": "Asha Brightvale", "exact": "true"}).json()
    asha = found["results"][0]
    history = client.get(f"/api/v1/characters/{asha['namespace']}/{asha['id']}/runs").json()
    assert history["items"][0]["dungeon"]["name"] == "Alcaz Prison"
    assert history["items"][0]["outcome"] == "completed"

    again = sync_once(home, cfg, state, uploader)
    assert again.batches_uploaded == 0 and again.new_versions == 0
