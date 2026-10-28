"""pytest entry point for the Lua addon tests."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import run_test_file, lua_test_files  # noqa: E402


@pytest.mark.parametrize("lua_file", lua_test_files(), ids=lambda p: p.stem)
def test_lua_suite(lua_file):
    results = run_test_file(lua_file)
    assert results, f"{lua_file.name} defined no tests"
    failures = [f"{r['name']}\n{r['err']}" for r in results if not r["ok"]]
    assert not failures, "\n\n".join(failures)
