"""Run ForeverTracker's Lua code in a real Lua 5.1 VM (via lupa) against the WoW mock.

Used by the addon unit tests (``test_addon.py``) and by the backend end-to-end tests, which
drive the actual addon through a dungeon scenario and upload the SavedVariables it writes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lupa import lua51

ADDON_TESTS = Path(__file__).resolve().parent
REPO = ADDON_TESTS.parents[1]
ADDON_ROOT = REPO / "addon" / "ForeverTracker"
LIB = ADDON_TESTS / "lib"


def new_runtime(seed: int = 20261026) -> Any:
    """A fresh Lua VM with the mock loaded. Each simulated installation needs its own seed,
    because the addon derives its random installation ID from math.random."""
    lua = lua51.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(f"Mock = {{ ROOT = [[{ADDON_ROOT.as_posix()}/]] }}")
    for name in ("wowmock.lua", "lunit.lua", "svwriter.lua"):
        lua.execute(f"dofile([[{(LIB / name).as_posix()}]])")
    lua.execute(f"Mock.reset(); math.randomseed({int(seed)})")  # reproducible installation IDs
    return lua


def run_test_file(path: Path) -> list[dict[str, Any]]:
    lua = new_runtime()
    lua.execute(f"dofile([[{path.as_posix()}]])")
    results = lua.eval("T.results")
    return [
        {"name": r["name"], "ok": bool(r["ok"]), "err": r["err"]}
        for r in (results[i] for i in range(1, len(results) + 1))
    ]


def lua_test_files() -> list[Path]:
    return sorted(ADDON_TESTS.glob("test_*.lua"))


def savedvariables_text(lua: Any) -> str:
    """Write the current mock 'file' the way the client would (after Mock.saveVariables())."""
    return lua.eval("SVWriter.serialize({ ForeverTrackerDB = Mock.saved })")


if __name__ == "__main__":
    import sys

    failed = 0
    for f in lua_test_files():
        for r in run_test_file(f):
            mark = "PASS" if r["ok"] else "FAIL"
            print(f"{mark}  {f.name}: {r['name']}")
            if not r["ok"]:
                failed += 1
                print("      " + (r["err"] or "").replace("\n", "\n      "))
    print(f"\n{'all passed' if not failed else f'{failed} failed'}")
    sys.exit(1 if failed else 0)
