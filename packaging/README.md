# Packaging: the one-download installer

This builds a single installer you host on your own website. Running it:

1. asks for the World of Warcraft: Forever game folder, `…\World of Warcraft\_forever_` (found through
   Battle.net's registry entry, so any drive works; the user confirms),
2. copies the **addon** into `…\Interface\AddOns\ForeverTracker` if it isn't there yet (the game
   enables it by default; players who came from CurseForge already have it),
3. installs **ForeverTrackerUploader.exe**, a windowless helper,
4. offers a ticked checkbox: *start with Windows and upload automatically*.

After that, every run uploads within a few seconds of a logout, exit or `/reload`, with nothing
for the player to click. There is no launcher and no tray icon.

Updates are split: **CurseForge updates the addon, and the app updates itself** (below). The installer
never overwrites an addon that is already installed, and uninstalling the app leaves the addon alone.

## How the "hands-off" part works, honestly

The uploader runs with **no window**, but it is **not hidden**:

- Start-with-Windows uses the per-user **Run key**, so it appears in **Settings → Apps → Startup**
  and **Task Manager → Startup**, where the player can switch it off.
- It appears in **Add/Remove Programs** with a working uninstaller.
- The process name is its real name; it is not disguised and does not resist being closed.

It is deliberately **not** a Windows service or a hidden scheduled task, because a background
program the user can't see or remove is what antivirus vendors, CurseForge and Blizzard treat as
malware — regardless of intent. Within these bounds, "runs quietly from boot" is fine.

The helper only ever **reads** the game's SavedVariables file; it never writes to the WoW folder.

## Build

From the repo root, in a Python 3.11+ environment:

```powershell
pip install -e uploader -e packages/savedvariables pyinstaller
.\packaging\build.ps1
```

Outputs land in `dist\`:
- `ForeverTrackerUploader.exe` — the helper
- `ForeverTracker-Setup-<version>.exe` — the installer (needs [Inno Setup 6](https://jrsoftware.org/isdl.php))

## Before you publish — one required edit and signing

1. **Server URL.** Edit `#define ServerURL` in `installer.iss` to your real site. The uploader
   refuses plain `http://` except for `localhost`, so it must be `https://`.
2. **Code signing (do not skip).** A windowless, autostarting, network-using exe is exactly the
   shape SmartScreen and antivirus flag on sight. Sign **both** the exe and the installer with an
   Authenticode certificate (an EV cert earns SmartScreen reputation fastest; open-source projects
   can apply to [SignPath](https://signpath.io/)):

   ```powershell
   signtool sign /tr http://timestamp.digicert.com /td sha256 /fd sha256 /a dist\ForeverTrackerUploader.exe
   signtool sign /tr http://timestamp.digicert.com /td sha256 /fd sha256 /a dist\ForeverTracker-Setup-0.1.0.exe
   ```

   Signing is the only thing here I can't do for you — it needs your certificate. Everything else
   is wired up and ready. It is also what makes self-update possible: an unsigned build never
   installs updates.

## How the app updates itself

Once a day the app asks the server for `/api/v1/uploader/latest`. If that names a newer version,
it downloads the installer, checks it against the published SHA-256, and runs it only if Windows
confirms a valid signature from **the same publisher as the installed app**. So a hacked server or
download host can't push its own program to players. The installer runs silently with `/UPDATE=1`:
it keeps the player's settings and autostart choice, doesn't touch the addon, and restarts the app.
`update-install.log` in `%APPDATA%\ForeverTracker\uploader\` records the last update.

## Releasing an update

1. Bump `__version__` in `uploader/forevertracker_uploader/__init__.py` (and `version` in
   `uploader/pyproject.toml`). `build.ps1` passes it to the installer, so they always match.
2. `.\packaging\build.ps1`, then sign both exes **with the same certificate subject as before**.
   A renewed certificate is fine; a different publisher name means installed apps refuse the update.
3. Host `dist\ForeverTracker-Setup-<version>.exe` over HTTPS (your site or a GitHub release), and
   hash the **signed** file: `Get-FileHash dist\ForeverTracker-Setup-<version>.exe -Algorithm SHA256`
4. Set these on the API server and restart it:

   ```
   UPLOADER_LATEST_VERSION=<version>
   UPLOADER_DOWNLOAD_URL=https://…/ForeverTracker-Setup-<version>.exe
   UPLOADER_SHA256=<hash from step 3>
   UPLOADER_SIGNED=true   # leave false for an unsigned build: the Download page then explains
                          # Windows' "unknown publisher" warning before the download starts
   ```

The website's Download page button switches to the new installer immediately; installed apps
update within a day.

## What the user can do after install

| Action | How |
|---|---|
| See it's running | Task Manager → Details → `ForeverTrackerUploader.exe` |
| Turn off auto-start | Settings → Apps → Startup → ForeverTracker → Off |
| Pause / check / see what's uploaded | `ForeverTrackerUploader.exe pause` / `status` / `disclose`, or re-run with `gui` from a source install |
| Read the log | `%APPDATA%\ForeverTracker\uploader\uploader.log` |
| Turn off self-update | Set `"auto_update": false` in `%APPDATA%\ForeverTracker\uploader\config.json` |
| Uninstall | Add/Remove Programs → ForeverTracker (the addon stays; remove it in CurseForge or the AddOns folder) |

> **Note:** the packaged exe excludes the Tkinter GUI to stay small and reduce antivirus noise, so
> `gui` works only from a `pip install` of the uploader, not from the bundled exe.

## Note on CurseForge

CurseForge distributes **addon files only** — it can't carry this exe, and it can't (and shouldn't)
launch a program. The addon lives on CurseForge; point players to your site's Download page for the
app, since the addon cannot upload anything on its own. CurseForge's moderation policy forbids
"external download links for files" but allows links to your own site at the bottom of the
description, so link to the Download page, not straight to the `.exe`.
