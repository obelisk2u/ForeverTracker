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
    catalog = json.loads((REPO / "backend" / "app" / "reconciliation" / "final_encounters.json").read_text(encoding="utf-8"))
    on_website = {int(map_id): {int(e) for e in d["final"]} for map_id, d in catalog["dungeons"].items()}
    assert in_addon == on_website
