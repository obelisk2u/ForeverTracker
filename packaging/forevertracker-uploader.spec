# PyInstaller spec for the ForeverTracker uploader.
#
# Build (from the repo root, with the uploader installed in the current environment):
#     pip install ./uploader ./packages/savedvariables pyinstaller   (not -e: PyInstaller misses editable installs)
#     pyinstaller packaging/forevertracker-uploader.spec --noconfirm
# Output: dist/ForeverTrackerUploader/ (ForeverTrackerUploader.exe, no console window, plus _internal/)
#
# console=False is what makes it windowless. It is NOT hidden: it has a tray icon, and it appears in
# Task Manager and (when start-with-Windows is on) in Settings > Apps > Startup.
#
# CI signs ForeverTrackerUploader.exe before the installer packs the folder (windows-app.yml); an unsigned,
# background, network-using exe is a magnet for SmartScreen and antivirus false positives.

import os
import re

from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

block_cipher = None
# The site's emblem. PyInstaller resolves relative paths against this spec's folder, so anchor it there.
ICON = os.path.join(SPECPATH, "..", "uploader", "forevertracker_uploader", "assets", "forevertracker.ico")

# Product name and version come from the uploader package, so every build carries the same metadata
# (SignPath enforces both on the files it signs).
with open(os.path.join("uploader", "forevertracker_uploader", "__init__.py"), encoding="utf-8") as fh:
    VERSION = re.search(r'^__version__ = "(.+)"', fh.read(), re.MULTILINE).group(1)
NUMBERS = tuple(int(p) for p in VERSION.split("."))
NUMBERS += (0,) * (4 - len(NUMBERS))
VERSION_INFO = VSVersionInfo(
    ffi=FixedFileInfo(filevers=NUMBERS, prodvers=NUMBERS),
    kids=[
        StringFileInfo(
            [
                StringTable(
                    "040904B0",
                    [
                        StringStruct("CompanyName", "ForeverTracker"),
                        StringStruct("FileDescription", "ForeverTracker desktop uploader"),
                        StringStruct("FileVersion", VERSION),
                        StringStruct("InternalName", "ForeverTrackerUploader"),
                        StringStruct("LegalCopyright", "Copyright (c) 2026 Jordan Stout. MIT License."),
                        StringStruct("OriginalFilename", "ForeverTrackerUploader.exe"),
                        StringStruct("ProductName", "ForeverTracker"),
                        StringStruct("ProductVersion", VERSION),
                    ],
                )
            ]
        ),
        VarFileInfo([VarStruct("Translation", [1033, 1200])]),
    ],
)

a = Analysis(
    ["uploader_entry.py"],
    pathex=["."],
    binaries=[],
    # The Start menu notice's emblem and font (forevertracker_uploader/assets). Tk stays in for that
    # notice; the background loop itself never opens a window.
    datas=collect_data_files("forevertracker_uploader"),
    hiddenimports=["forevertracker_sv"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# A folder (one-dir), not a single self-extracting exe: a one-file exe unpacks itself into %TEMP% on every
# start, which is what antivirus heuristics (Norton's among them) flag. The installer copies the folder once.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ForeverTrackerUploader",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=ICON,
    version=VERSION_INFO,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="ForeverTrackerUploader",
)
