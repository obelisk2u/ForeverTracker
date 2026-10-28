import json
import os
import sys
import time
from pathlib import Path

import httpx
import pytest
from forevertracker_sv.writer import to_savedvariables

from forevertracker_uploader import autostart, background, files
from forevertracker_uploader.cli import main
from forevertracker_uploader.client import Uploader, check_server_url
from forevertracker_uploader.config import Config, State
from forevertracker_uploader.singleinstance import AlreadyRunning, SingleInstance
from forevertracker_uploader.sync import disclose, sync_once

T0 = 1_792_000_000


def run(oid: str, rev: int = 1) -> dict:
    return {
        "type": "dungeon_run",
        "observation_id": oid,
        "revision": rev,
        "state": "completed",
        "recorded_by": {"name": "Autumn", "surname": "Redleaf"},
        "roster": [{"ref": "u1", "name": "Autumn", "surname": "Redleaf"}, {"ref": "u2", "name": "Mah", "surname": "Beardlong"}],
        "timing": {"started_at": T0, "ended_at": T0 + 1800, "last_updated_at": T0 + 1800},
    }


def write_sv(path: Path, observations: list[dict], installation: str = "ft-0123456789abcdef") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = {
        "format": "forevertracker.savedvariables",
        "schema_version": 1,
        "installation_id": installation,
        "addon_version": "0.1.0",
        "observations": observations,
    }
    path.write_text(to_savedvariables({"ForeverTrackerDB": db}), encoding="utf-8")
    old = time.time() - 60
    os.utime(path, (old, old))  # written a minute ago: stable


@pytest.fixture
def wow(tmp_path):
    flavor = tmp_path / "World of Warcraft" / "_forever_"
    sv = flavor / "WTF" / "Account" / "123#1" / "SavedVariables" / "ForeverTracker.lua"
    write_sv(sv, [run("r-1")])
    (flavor / "Interface" / "AddOns").mkdir(parents=True)
    return tmp_path / "World of Warcraft", sv


class FakeServer:
    def __init__(self, statuses=None):
        self.statuses = list(statuses or [])
        self.received: list[dict] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["X-ForeverTracker-Client"].startswith("uploader/")
        status = self.statuses.pop(0) if self.statuses else 200
        if status != 200:
            return httpx.Response(status, json={"detail": "nope"})
        batch = json.loads(request.content)
        self.received.append(batch)
        return httpx.Response(
            200,
            json={"status": "processed", "observations": [{"status": "accepted"} for _ in batch["observations"]]},
        )

    def uploader(self, **kw) -> Uploader:
        return Uploader("https://ft.test", transport=httpx.MockTransport(self.handler), sleep=lambda s: None, **kw)


def snapshot(folder: Path) -> dict[str, tuple[int, int]]:
    return {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in folder.rglob("*") if p.is_file()}


def test_finds_files_from_root_flavor_or_file(wow):
    root, sv = wow
    assert files.find_savedvariables([root]) == [sv]
    assert files.find_savedvariables([root / "_forever_"]) == [sv]
    assert files.find_savedvariables([sv]) == [sv]
    assert files.find_savedvariables([root / "missing"]) == []


def test_sync_uploads_once_and_never_touches_the_wow_folder(wow, tmp_path):
    root, _ = wow
    home = tmp_path / "home"
    cfg, state, server = Config(wow_paths=[str(root)]), State(), FakeServer()
    before = snapshot(root)
    report = sync_once(home, cfg, state, server.uploader())
    assert report.batches_uploaded == 1 and report.observations == {"accepted": 1}
    assert len(server.received) == 1
    again = sync_once(home, cfg, state, server.uploader())
    assert again.batches_uploaded == 0 and len(server.received) == 1
    assert snapshot(root) == before
    assert state.last_sync_at is not None and state.last_sync_result.startswith("0 batch(es) uploaded")


def test_overwritten_file_versions_are_archived_and_all_uploaded(wow, tmp_path):
    """If the client fails to load saved data, each session overwrites the file with only its own runs."""
    root, sv = wow
    home = tmp_path / "home"
    cfg, state, server = Config(wow_paths=[str(root)]), State(), FakeServer(statuses=[503, 503, 503, 503, 503])
    sync_once(home, cfg, state, server.uploader())  # server down: version 1 stays pending
    assert server.received == []
    write_sv(sv, [run("r-2")], installation="ft-fedcba9876543210")  # next session overwrote the file
    sync_once(home, cfg, state, server.uploader())
    ids = sorted(o["observation_id"] for b in server.received for o in b["observations"])
    assert ids == ["r-1", "r-2"]
    assert len(list((home / "archive").glob("*.lua"))) == 2


def test_permanent_rejections_are_not_retried_forever(wow, tmp_path):
    root, _ = wow
    home = tmp_path / "home"
    cfg, state, server = Config(wow_paths=[str(root)]), State(), FakeServer(statuses=[422])
    report = sync_once(home, cfg, state, server.uploader())
    assert report.errors and "HTTP 422" in report.errors[0]
    assert list(state.uploaded_batches.values()) == ["rejected"]
    again = sync_once(home, cfg, state, server.uploader())
    assert again.batches_uploaded == 0 and again.errors == [] and server.received == []  # not sent again


def test_temporary_failures_are_retried_with_backoff():
    server = FakeServer(statuses=[503, 429])
    delays = []
    up = Uploader("https://ft.test", transport=httpx.MockTransport(server.handler), sleep=delays.append)
    result = up.upload_batch(json.dumps({"observations": []}).encode())
    assert result["status"] == "processed"
    assert delays == [1.0, 2.0]


def test_requires_https_except_localhost():
    assert check_server_url("https://forevertracker.example/") == "https://forevertracker.example"
    assert check_server_url("http://localhost:8000") == "http://localhost:8000"
    with pytest.raises(ValueError):
        check_server_url("http://forevertracker.example")


def test_pause_stops_uploads(wow, tmp_path):
    root, _ = wow
    server = FakeServer()
    report = sync_once(tmp_path / "home", Config(wow_paths=[str(root)], paused=True), State(), server.uploader())
    assert report.paused and server.received == []


def test_waits_for_a_file_that_is_being_written(wow, tmp_path):
    root, sv = wow
    sv.touch()  # modified just now
    calls = []

    def sleep_and_write(seconds):
        calls.append(seconds)
        with open(sv, "a", encoding="utf-8") as f:
            f.write("\n")  # the client is still writing

    assert files.is_stable(sv, 5, sleep=sleep_and_write) is False
    assert calls


def test_disclose_lists_what_would_be_sent(wow):
    root, _ = wow
    lines = "\n".join(disclose(Config(wow_paths=[str(root)])))
    assert "Autumn Redleaf" in lines and "Mah Beardlong" in lines
    assert "no account name" in lines
    assert "Would send 1 batch(es)" in lines


def test_cli_setup_and_status(wow, tmp_path, capsys):
    root, _ = wow
    home = tmp_path / "home"
    assert main(["--home", str(home), "setup", "--wow", str(root), "--server", "http://localhost:8000"]) == 0
    assert main(["--home", str(home), "pause"]) == 0
    assert Config.load(home).paused is True
    assert main(["--home", str(home), "status"]) == 0
    out = capsys.readouterr().out
    assert "ForeverTracker.lua" in out and "Paused:        yes" in out


def test_single_instance_lock_blocks_a_second_copy(tmp_path):
    home = tmp_path / "home"
    first = SingleInstance(home).acquire()
    try:
        with pytest.raises(AlreadyRunning):
            SingleInstance(home).acquire()
    finally:
        first.release()
    SingleInstance(home).acquire().release()  # released: the next start succeeds


def test_autostart_command_targets_windowless_background_mode(monkeypatch):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Python\python.exe", raising=False)
    cmd = autostart.run_command()
    assert cmd.endswith("background")
    assert "pythonw.exe" in cmd and "forevertracker_uploader.cli" in cmd
    assert "--home" in autostart.run_command(Path(r"C:\home dir"))


def test_autostart_command_for_a_frozen_exe_is_just_the_exe(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Program Files\ForeverTracker\ForeverTrackerUploader.exe", raising=False)
    assert autostart.run_command() == '"C:\\Program Files\\ForeverTracker\\ForeverTrackerUploader.exe" background'


@pytest.mark.skipif(sys.platform != "win32", reason="Run key is Windows-only")
def test_autostart_enable_status_disable_roundtrip():
    import winreg

    subkey = r"Software\ForeverTracker\_pytest_run"
    name = "ForeverTrackerUploaderTest"
    try:
        assert autostart.status(subkey=subkey, value_name=name) is None
        autostart.enable(command='"x.exe" background', subkey=subkey, value_name=name)
        assert autostart.status(subkey=subkey, value_name=name) == '"x.exe" background'
        assert autostart.disable(subkey=subkey, value_name=name) is True
        assert autostart.status(subkey=subkey, value_name=name) is None
        assert autostart.disable(subkey=subkey, value_name=name) is False
    finally:
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, subkey)
        except OSError:
            pass


def test_background_uploads_on_first_pass_then_only_on_change(wow, tmp_path):
    root, sv = wow
    home = tmp_path / "home"
    Config(wow_paths=[str(root)], server_url="https://ft.test", poll_seconds=0).save(home)
    server = FakeServer()
    factory = lambda _url: server.uploader()  # noqa: E731

    # First pass sends the one run; a second idle pass sends nothing (file unchanged).
    passes = background.run_background(home, iterations=2, sleep=lambda _s: None, uploader_factory=factory, retry_every=999)
    assert passes == 1 and len(server.received) == 1

    # A new session overwrites the file; the next pass picks it up.
    write_sv(sv, [run("r-2")], installation="ft-fedcba9876543210")
    more = background.run_background(home, iterations=1, sleep=lambda _s: None, uploader_factory=factory, retry_every=999)
    assert more == 1
    ids = sorted(o["observation_id"] for b in server.received for o in b["observations"])
    assert ids == ["r-1", "r-2"]


def test_background_paused_uploads_nothing(wow, tmp_path):
    root, _ = wow
    home = tmp_path / "home"
    Config(wow_paths=[str(root)], server_url="https://ft.test", paused=True, poll_seconds=0).save(home)
    server = FakeServer()
    passes = background.run_background(
        home, iterations=2, sleep=lambda _s: None, uploader_factory=lambda _u: server.uploader(), retry_every=999
    )
    assert passes == 0 and server.received == []
