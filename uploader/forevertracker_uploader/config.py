from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path


def default_home() -> Path:
    override = os.environ.get("FOREVERTRACKER_UPLOADER_HOME")
    if override:
        return Path(override)
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home())) / "ForeverTracker" / "uploader"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "ForeverTracker" / "uploader"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "forevertracker" / "uploader"


@dataclass
class Config:
    server_url: str = "https://forevertracker.org"
    wow_paths: list[str] = field(default_factory=list)  # game folders (e.g. ...\_forever_) or explicit files
    paused: bool = False
    poll_seconds: float = 10.0
    stability_seconds: float = 5.0
    upload_archived_versions: bool = True
    auto_update: bool = True  # packaged Windows app only; see update.py

    @classmethod
    def load(cls, home: Path) -> "Config":
        path = home / "config.json"
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known)

    def save(self, home: Path) -> None:
        home.mkdir(parents=True, exist_ok=True)
        (home / "config.json").write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")


@dataclass
class State:
    uploaded_batches: dict[str, str] = field(default_factory=dict)  # batch_id -> upload result status
    versions: dict[str, dict] = field(default_factory=dict)  # sha256 -> {source, archived_at, processed}
    last_sync_at: float | None = None
    last_sync_result: str | None = None
    last_error: str | None = None

    @classmethod
    def load(cls, home: Path) -> "State":
        path = home / "state.json"
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def save(self, home: Path) -> None:
        home.mkdir(parents=True, exist_ok=True)
        tmp = home / "state.json.tmp"
        tmp.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        tmp.replace(home / "state.json")
