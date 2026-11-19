"""The app keeps the ForeverTracker addon up to date with the copy it carries (addon.py)."""

import os
import sys
from pathlib import Path

import pytest

from forevertracker_uploader import addon, background
from forevertracker_uploader.config import Config


def write_addon(folder: Path, version: str, files: dict[str, str]) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "ForeverTracker.toc").write_text(f"## Interface: 16001\n## Title: ForeverTracker\n## Version: {version}\n", encoding="utf-8")
    for name, text in files.items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text(text, encoding="utf-8")
    return folder


@pytest.fixture
def game(tmp_path):
    """A World of Warcraft install with Forever's flavor folder and addon 0.2.12 in it."""
    flavor = tmp_path / "World of Warcraft" / "_forever_"
    (flavor / "WTF" / "Account" / "ACCOUNT" / "SavedVariables").mkdir(parents=True)
    (flavor / "Wow.exe").write_bytes(b"MZ")
    installed = write_addon(flavor / "Interface" / "AddOns" / "ForeverTracker", "0.2.12", {"Core/Old.lua": "old", "Init.lua": "v12"})
    (flavor / "Interface" / "AddOns" / "SomeOtherAddon").mkdir()
    return flavor, installed


@pytest.fixture
def carried(tmp_path):
    """The copy the installer left in the app's folder: addon 0.2.13."""
    return write_addon(tmp_path / "app" / "addon" / "ForeverTracker", "0.2.13", {"Core/New.lua": "new", "Init.lua": "v13"})


def keep(game_path, source, **kw):
    return addon.keep_updated(Config(wow_paths=[str(game_path)], **kw), source=source, is_running=lambda _f: False)


def test_replaces_an_older_addon_with_the_copy_it_carries(game, carried):
    flavor, installed = game
    assert keep(flavor, carried) == [installed]
    assert addon.toc_version(installed) == (0, 2, 13)
    assert (installed / "Init.lua").read_text() == "v13"
    assert (installed / "Core" / "New.lua").is_file()
    assert not (installed / "Core" / "Old.lua").exists(), "files the new version dropped are gone"
    assert sorted(p.name for p in installed.parent.iterdir()) == ["ForeverTracker", "SomeOtherAddon"], "nothing else touched or left"
    assert keep(flavor, carried) == [], "once"


@pytest.mark.parametrize("configured", ["root", "flavor", "savedvariables"])
def test_finds_the_addon_from_any_configured_game_path(game, carried, configured):
    flavor, installed = game
    sv = flavor / "WTF" / "Account" / "ACCOUNT" / "SavedVariables" / "ForeverTracker.lua"
    sv.write_text("ForeverTrackerDB = {}", encoding="utf-8")
    path = {"root": flavor.parent, "flavor": flavor, "savedvariables": sv}[configured]
    assert keep(path, carried) == [installed]


def test_waits_while_the_game_is_running(game, carried):
    flavor, installed = game
    running = [True]
    cfg = Config(wow_paths=[str(flavor)])
    assert addon.keep_updated(cfg, source=carried, is_running=lambda f: running[0]) == []
    assert addon.toc_version(installed) == (0, 2, 12)
    running[0] = False
    assert addon.keep_updated(cfg, source=carried, is_running=lambda f: running[0]) == [installed]


@pytest.mark.parametrize("version", ["0.2.13", "0.2.14", "1.0.0"])
def test_never_replaces_the_same_or_a_newer_version(game, carried, version):
    flavor, installed = game
    write_addon(installed, version, {"Init.lua": "mine"})
    assert keep(flavor, carried) == []
    assert (installed / "Init.lua").read_text() == "mine"


def test_never_puts_back_an_addon_the_player_removed(game, carried):
    flavor, installed = game
    for p in sorted(installed.rglob("*"), reverse=True):
        p.unlink() if p.is_file() else p.rmdir()
    installed.rmdir()
    assert keep(flavor, carried) == []
    assert not installed.exists()


def test_leaves_an_addon_without_a_readable_version_alone(game, carried):
    flavor, installed = game
    (installed / "ForeverTracker.toc").write_text("## Title: ForeverTracker\n", encoding="utf-8")
    assert keep(flavor, carried) == []


def test_can_be_switched_off(game, carried):
    flavor, installed = game
    assert keep(flavor, carried, update_addon=False) == []
    assert addon.toc_version(installed) == (0, 2, 12)


def test_an_interrupted_swap_leaves_the_old_version_in_place(game, carried, monkeypatch):
    flavor, installed = game
    real = os.replace
    calls = []

    def flaky(src, dst):
        calls.append(src)
        if len(calls) == 2:  # moving the new copy in fails, e.g. a file in the folder is open
            raise PermissionError("in use")
        return real(src, dst)

    monkeypatch.setattr(addon.os, "replace", flaky)
    with pytest.raises(PermissionError):
        keep(flavor, carried)
    assert addon.toc_version(installed) == (0, 2, 12)
    assert (installed / "Core" / "Old.lua").is_file()
    assert sorted(p.name for p in installed.parent.iterdir()) == ["ForeverTracker", "SomeOtherAddon"]


def test_only_the_packaged_app_carries_an_addon():
    assert addon.bundled_addon() is None  # tests run from source, not the packaged exe
    assert addon.keeper_for_this_build() is None


@pytest.mark.skipif(sys.platform != "win32", reason="Windows process list")
def test_sees_running_programs_and_a_running_game(tmp_path):
    assert Path(sys.executable).name.lower() in addon.running_programs()
    flavor = tmp_path / "_forever_"
    flavor.mkdir()
    (flavor / Path(sys.executable).name).write_bytes(b"MZ")  # this very program "is" the game
    assert addon.game_running(flavor)
    (flavor / Path(sys.executable).name).unlink()
    (flavor / "Wow.exe").write_bytes(b"MZ")
    assert not addon.game_running(flavor) or "wow.exe" in addon.running_programs()


def test_background_checks_the_addon_at_start_and_every_minute(tmp_path):
    home = tmp_path / "home"
    Config(server_url="https://ft.test", poll_seconds=0).save(home)
    now = [0.0]
    checks = []

    def ten_seconds_pass(_seconds):
        now[0] += 10

    background.run_background(
        home, iterations=13, sleep=ten_seconds_pass, addon_keeper=lambda cfg: checks.append(now[0]), clock=lambda: now[0]
    )
    assert checks == [0.0, 60.0, 120.0]


def test_a_failing_addon_update_does_not_stop_the_loop(tmp_path):
    home = tmp_path / "home"
    Config(server_url="https://ft.test", poll_seconds=0).save(home)
    calls = []

    def broken(_cfg):
        calls.append(1)
        raise PermissionError("in use")

    background.run_background(home, iterations=3, sleep=lambda _s: None, addon_keeper=broken, addon_every=0)
    assert len(calls) == 3
