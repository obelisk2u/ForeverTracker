import hashlib
import sys
from pathlib import Path

import httpx
import pytest

from forevertracker_uploader import __version__, background, update
from forevertracker_uploader.config import Config
from forevertracker_uploader.singleinstance import SingleInstance

INSTALLER = b"MZ pretend installer"
SHA = hashlib.sha256(INSTALLER).hexdigest()
SETUP = "ForeverTracker-Setup-9.9.9.exe"
PUBLISHER = "CN=ForeverTracker, O=ForeverTracker"


def server(version="9.9.9", sha=SHA, url=f"https://downloads.ft.test/{SETUP}", published=True):
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        if request.url.path == "/api/v1/uploader/latest":
            if not published:
                return httpx.Response(404, json={"detail": "no desktop app release published"})
            return httpx.Response(200, json={"version": version, "download_url": url, "sha256": sha})
        return httpx.Response(200, content=INSTALLER)

    return httpx.MockTransport(handler), requests


def install(home: Path, transport, signers: dict[str, str]):
    launched: list[list[str]] = []
    started = update.check_and_install(
        home,
        "https://ft.test",
        current_exe=Path("ForeverTrackerUploader.exe"),
        transport=transport,
        signed_by=lambda p: signers.get(p.name),
        launch=lambda args, **_kw: launched.append(args),
    )
    return started, launched


SIGNED = {"ForeverTrackerUploader.exe": PUBLISHER, SETUP: PUBLISHER}


def test_versions_compare_numerically():
    assert update.parse_version("0.10.0") > update.parse_version("0.9.9")
    with pytest.raises(ValueError):
        update.parse_version("1.0-beta")


def test_installs_a_newer_release_signed_by_the_same_publisher(tmp_path):
    transport, _ = server()
    started, launched = install(tmp_path, transport, SIGNED)
    assert started
    (args,) = launched
    assert Path(args[0]) == tmp_path / "updates" / SETUP and Path(args[0]).read_bytes() == INSTALLER
    assert "/VERYSILENT" in args and "/UPDATE=1" in args


def test_nothing_happens_without_a_newer_release(tmp_path):
    for transport, requests in (server(version=__version__), server(published=False)):
        assert install(tmp_path, transport, SIGNED) == (False, [])
        assert requests == ["/api/v1/uploader/latest"]  # nothing downloaded


def test_an_unsigned_build_never_downloads_or_installs(tmp_path):
    transport, requests = server()
    assert install(tmp_path, transport, {}) == (False, [])
    assert requests == ["/api/v1/uploader/latest"]


@pytest.mark.skipif(sys.platform != "win32", reason="Authenticode is Windows-only")
def test_reads_the_publisher_of_a_signed_file_from_windows(tmp_path):
    # The Python running the tests is signed by its publisher (python.org builds are).
    assert "CN=Python Software Foundation" in update.signer(Path(sys.base_prefix) / "python.exe")
    unsigned = tmp_path / "unsigned.exe"
    unsigned.write_bytes(INSTALLER)
    assert update.signer(unsigned) is None
    assert update.signer(tmp_path / "missing.exe") is None


def test_rejects_an_installer_from_another_publisher(tmp_path):
    transport, _ = server()
    launched: list = []
    with pytest.raises(update.UpdateError):
        update.check_and_install(
            tmp_path,
            "https://ft.test",
            current_exe=Path("ForeverTrackerUploader.exe"),
            transport=transport,
            signed_by=lambda p: {"ForeverTrackerUploader.exe": PUBLISHER, SETUP: "CN=Someone Else"}.get(p.name),
            launch=lambda args, **_kw: launched.append(args),
        )
    assert launched == [] and not (tmp_path / "updates" / SETUP).exists()


def test_rejects_a_download_that_does_not_match_the_published_hash(tmp_path):
    transport, _ = server(sha="0" * 64)
    with pytest.raises(update.UpdateError):
        install(tmp_path, transport, SIGNED)
    assert not (tmp_path / "updates" / SETUP).exists()


def test_requires_an_https_download(tmp_path):
    transport, _ = server(url=f"http://downloads.ft.test/{SETUP}")
    with pytest.raises(ValueError):
        install(tmp_path, transport, SIGNED)


def test_background_checks_daily_and_exits_to_let_the_installer_run(tmp_path):
    home = tmp_path / "home"
    Config(server_url="https://ft.test", poll_seconds=0).save(home)
    now = [0.0]
    checks: list[float] = []

    def updater(_home, _cfg):
        checks.append(now[0])
        return now[0] >= 86_400  # a release appears a day later

    def an_hour_passes(_seconds):
        now[0] += 3600

    background.run_background(home, iterations=100, sleep=an_hour_passes, updater=updater, clock=lambda: now[0])
    assert checks == [0.0, 86_400.0]
    SingleInstance(home).acquire().release()  # the lock is free for the new version


def test_a_failing_update_check_does_not_stop_the_loop(tmp_path):
    home = tmp_path / "home"
    Config(server_url="https://ft.test", poll_seconds=0).save(home)

    def broken(_home, _cfg):
        raise httpx.ConnectError("offline")

    background.run_background(home, iterations=3, sleep=lambda _s: None, updater=broken, update_every=0)
