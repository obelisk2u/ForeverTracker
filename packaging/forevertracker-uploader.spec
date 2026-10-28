# PyInstaller spec for the ForeverTracker uploader.
#
# Build (from the repo root, with the uploader installed in the current environment):
#     pip install -e uploader -e packages/savedvariables pyinstaller
#     pyinstaller packaging/forevertracker-uploader.spec --noconfirm
# Output: dist/ForeverTrackerUploader.exe  (single file, no console window)
#
# console=False is what makes it windowless. It is NOT hidden: once installed it appears in
# Task Manager and (when start-with-Windows is on) in Settings > Apps > Startup.
#
# Sign the result before distributing it; an unsigned, windowless, network-using exe is a magnet
# for SmartScreen and antivirus false positives:
#     signtool sign /tr http://timestamp.digicert.com /td sha256 /fd sha256 /a dist\ForeverTrackerUploader.exe

import os

block_cipher = None
ICON = os.path.join("packaging", "forevertracker.ico")  # optional; falls back to the default icon

a = Analysis(
    ["uploader_entry.py"],
    pathex=["."],
    binaries=[],
    datas=[],
    hiddenimports=["forevertracker_sv"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter"],  # the background app has no GUI; drop tk to shrink the exe and reduce AV noise
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="ForeverTrackerUploader",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    icon=ICON if os.path.exists(ICON) else None,
    version="packaging/version_info.txt" if os.path.exists("packaging/version_info.txt") else None,
)
