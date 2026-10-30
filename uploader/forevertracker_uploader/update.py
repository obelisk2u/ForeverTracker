"""Self-update for the packaged Windows app.

Once a day the background app asks its server for the newest release (``/api/v1/uploader/latest``).
A newer installer is downloaded, checked against the SHA-256 the server published, and run only if
Windows reports a valid Authenticode signature from the same publisher as the running exe, so a
compromised server or download host cannot push its own program. The installer runs silently with
``/UPDATE=1``: it keeps the player's settings, never touches the addon (CurseForge updates that),
and starts the new version.

Only the packaged exe updates itself. A pip install is updated with pip, and an unsigned build
(every development build) never installs anything.
"""

from __future__ import annotations

import hashlib
import logging
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import httpx

from forevertracker_uploader import __version__
from forevertracker_uploader.client import check_server_url

log = logging.getLogger("forevertracker.uploader.update")

INSTALLER_ARGS = ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/UPDATE=1"]
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class UpdateError(Exception):
    pass


@dataclass
class Release:
    version: str
    download_url: str
    sha256: str


def parse_version(version: str) -> tuple[int, ...]:
    """'0.10.2' -> (0, 10, 2). Anything else raises ValueError."""
    parts = version.strip().split(".")
    if not all(p.isdigit() for p in parts):
        raise ValueError(f"not a version number: {version!r}")
    return tuple(int(p) for p in parts)


def is_newer(release: Release, current: str = __version__) -> bool:
    return parse_version(release.version) > parse_version(current)


def _client(transport: httpx.BaseTransport | None) -> httpx.Client:
    return httpx.Client(
        transport=transport, timeout=60.0, follow_redirects=True, headers={"X-ForeverTracker-Client": f"uploader/{__version__}"}
    )


def fetch_latest(server_url: str, *, transport: httpx.BaseTransport | None = None) -> Release | None:
    """The newest published release, or None if the server publishes none."""
    with _client(transport) as client:
        res = client.get(f"{check_server_url(server_url)}/api/v1/uploader/latest")
    if res.status_code == 404:
        return None
    res.raise_for_status()
    data = res.json()
    release = Release(
        version=str(data["version"]),
        download_url=check_server_url(str(data["download_url"])),
        sha256=str(data["sha256"]).lower(),
    )
    parse_version(release.version)
    if not _SHA256.match(release.sha256):
        raise UpdateError("the server published an invalid SHA-256")
    return release


def download(release: Release, folder: Path, *, transport: httpx.BaseTransport | None = None) -> Path:
    """Download the installer into ``folder`` and verify its SHA-256. Earlier downloads are removed."""
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.iterdir():
        try:
            old.unlink()
        except OSError:
            pass  # e.g. an installer that is still running
    path = folder / f"ForeverTracker-Setup-{release.version}.exe"
    digest = hashlib.sha256()
    with _client(transport) as client, client.stream("GET", release.download_url) as res:
        res.raise_for_status()
        with open(path, "wb") as fh:
            for chunk in res.iter_bytes():
                digest.update(chunk)
                fh.write(chunk)
    if digest.hexdigest() != release.sha256:
        path.unlink(missing_ok=True)
        raise UpdateError(f"the download does not match the published SHA-256 ({release.download_url})")
    return path


def signer(path: Path) -> str | None:
    """The certificate subject of a valid Authenticode signature on ``path``, else None (Windows only)."""
    if sys.platform != "win32":
        return None
    from forevertracker_uploader import authenticode

    try:
        return authenticode.signer(path)
    except OSError:
        return None


def _detached() -> dict:
    if sys.platform == "win32":
        return {"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP, "close_fds": True}
    return {"start_new_session": True}


def check_and_install(
    home: Path,
    server_url: str,
    *,
    current_exe: Path | None = None,
    transport: httpx.BaseTransport | None = None,
    signed_by=signer,
    launch=subprocess.Popen,
) -> bool:
    """Start the installer of a newer release, if there is one.

    True means the installer is running and this process should exit so its exe can be replaced.
    """
    release = fetch_latest(server_url, transport=transport)
    if release is None or not is_newer(release):
        return False
    publisher = signed_by(current_exe or Path(sys.executable))
    if not publisher:
        log.info("update %s is available, but this build is unsigned and never installs updates", release.version)
        return False
    installer = download(release, home / "updates", transport=transport)
    if signed_by(installer) != publisher:
        installer.unlink(missing_ok=True)
        raise UpdateError(f"update {release.version} is not signed by {publisher!r}; not installing it")
    log.info("installing update %s (this is %s)", release.version, __version__)
    launch([str(installer), *INSTALLER_ARGS, f"/LOG={home / 'update-install.log'}"], **_detached())
    return True


def updater_for_this_build():
    """The background loop's update check, or None: only the packaged Windows exe updates itself."""
    if getattr(sys, "frozen", False) and sys.platform == "win32":
        return lambda home, cfg: cfg.auto_update and check_and_install(home, cfg.server_url)
    return None
