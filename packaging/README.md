# Packaging: the one-download installer

This builds a single installer you host on your own website. Running it:

1. asks for the World of Warcraft: Forever game folder, `…\World of Warcraft\_forever_`, filled in from
   Battle.net's registry entry, Windows' list of installed programs, or common folders on every fixed drive.
   A downloaded but never-played game counts (it has `Wow.exe`, not yet `Interface` or `WTF`); the user
   confirms or browses,
2. copies the **addon** into `…\Interface\AddOns\ForeverTracker` if it isn't there yet (the game
   enables it by default; players who came from CurseForge already have it),
3. installs **ForeverTrackerUploader.exe**, a background app with a tray icon, and a **ForeverTracker**
   Start menu shortcut (which is what Windows search finds),
4. offers a ticked checkbox, *start with Windows and upload automatically*, and an unticked one for a
   desktop shortcut,
5. ends with a ticked *Start ForeverTracker* box.

After that, every run uploads within a few seconds of a logout, exit or `/reload`, with nothing
for the player to click. The shortcuts start the app (or say it is already running) with a small
card in the site's style. While it runs, its tray icon opens a card with its status, when it last
synced, and **Quit ForeverTracker**. On Windows 11 a new tray icon starts in the overflow (the ^
arrow) until the player pins it.

Updates are split: **CurseForge updates the addon, and the app updates itself** (below). The installer
never overwrites an addon that is already installed, and uninstalling the app leaves the addon alone.

## How the "hands-off" part works, honestly

The uploader runs with **no window**, but it is **not hidden**:

- Its **tray icon** shows it is running and quits it in one click.
- Start-with-Windows uses the per-user **Run key**, so it appears in **Settings → Apps → Startup**
  and **Task Manager → Startup**, where the player can switch it off.
- It appears in **Add/Remove Programs** with a working uninstaller.
- The process name is its real name; it is not disguised and does not resist being closed.

It is deliberately **not** a Windows service or a hidden scheduled task, because a background
program the user can't see or remove is what antivirus vendors, CurseForge and Blizzard treat as
malware — regardless of intent. Within these bounds, "runs quietly from boot" is fine.

The helper only ever **reads** the game's SavedVariables file; it never writes to the WoW folder.

## Build

**Release builds come from GitHub Actions** ([`windows-app.yml`](../.github/workflows/windows-app.yml)): every push
to `main` that touches the app, addon or packaging builds the app on a clean Windows runner, signs it with
[Azure Artifact Signing](https://azure.microsoft.com/products/artifact-signing), packs it into the installer, signs
the installer, checks both signatures, and uploads them as the `ForeverTracker-windows-signed` artifact. Pull
requests and other branches build the same thing unsigned (`ForeverTracker-windows-unsigned`).

Signing matters: a background, autostarting, network-using exe is exactly the shape SmartScreen and antivirus
flag, and an unsigned build never installs updates. The one-time setup, all in Azure and GitHub, with no password
or key stored anywhere:

- Artifact Signing account `forevertracker` (East US) with a **Public Trust** certificate profile `forevertracker`
  on the maintainer's validated identity, so Windows shows the publisher as that name.
- A Microsoft Entra app registration with a **federated credential** for this repository's `main` branch and the
  *Artifact Signing Certificate Profile Signer* role on the signing account.
- Repository variables `AZURE_CLIENT_ID` (the app registration's *Application (client) ID*, not its Object ID)
  and `AZURE_TENANT_ID`. Without them the workflow still builds, unsigned.

To build locally instead, from the repo root in a Python 3.11+ environment:

```powershell
pip install ./packages/savedvariables ./uploader pyinstaller==6.11.1
.\packaging\build.ps1                 # or -Stage app / -Stage installer for one half
```

Outputs land in `dist\`:
- `ForeverTrackerUploader\` — the app: `ForeverTrackerUploader.exe` (product name and version are stamped from
  `__version__`) and its `_internal\` folder
- `ForeverTracker-Setup-<version>.exe` — the installer (needs [Inno Setup 6](https://jrsoftware.org/isdl.php)); it
  shows [`privacy.txt`](privacy.txt) before installing. Local builds are unsigned.

## Antivirus false positives

A new Python app that starts with Windows and uploads data looks suspicious to antivirus heuristics until it
has a reputation. What keeps the score low:

- **A folder, not a one-file exe.** A PyInstaller one-file exe unpacks itself into `%TEMP%` on every start,
  which heuristics (Norton's among them) treat as malware behaviour. The installer copies the folder once.
- **A launcher compiled from source.** PyInstaller's prebuilt launcher is shared with malware, so signatures
  match it; CI builds its own (`PYINSTALLER_COMPILE_BOOTLOADER`).
- **No hidden programs or scripts.** The installer leaves its settings (server, game folder) in
  `%APPDATA%\ForeverTracker\uploader\installer.json` for the app to pick up, instead of running the new app hidden,
  and never starts PowerShell. The app checks update signatures with the Windows API (`WinVerifyTrust`), not
  PowerShell. Heuristics treat a new download that starts hidden scripts as malware, and remove everything it
  installed.
- **Signed** app and installer, with the same publisher every release.
- **Submit each new release** as a false positive, before announcing it: Norton
  (<https://submit.norton.com/>, as a false positive) and Microsoft Defender
  (<https://www.microsoft.com/wdsi/filesubmission>).
  Submit the installer from the GitHub release. Reputation builds as people install it.

If a player sees "Windows cannot access the specified device, path, or file", their antivirus has quarantined
or is holding the file named in the title bar (the installer or the app): check its history or quarantine,
restore the file and allow it, and note the detection name. Every install also writes
`%TEMP%\Setup Log <date> #<n>.txt`, which shows how far it got.

## How the app updates itself

Once a day the app asks the server for `/api/v1/uploader/latest`. If that names a newer version,
it downloads the installer, checks it against the published SHA-256, and runs it only if Windows
confirms a valid signature from **the same publisher as the installed app**. So a hacked server or
download host can't push its own program to players. The installer runs silently with `/UPDATE=1`:
it keeps the player's settings and autostart choice, doesn't touch the addon, and restarts the app.
`update-install.log` in `%APPDATA%\ForeverTracker\uploader\` records the last update.

## Releasing an update

1. Bump `__version__` in `uploader/forevertracker_uploader/__init__.py` (and `version` in
   `uploader/pyproject.toml`). `build.ps1` passes it to the installer, so they always match. Push to `main`.
2. On GitHub: **Actions → Windows app → Run workflow** (branch `main`), tick **Publish**. It builds, signs, and
   creates the release `v<version>` with the signed installer attached. It refuses to publish an unsigned build.
3. The run's summary lists four settings. Put them in the server's `.env` and restart the backend
   (`docker compose -f docker-compose.prod.yml --env-file .env up -d backend`):

   ```
   UPLOADER_LATEST_VERSION=<version>
   UPLOADER_DOWNLOAD_URL=https://github.com/obelisk2u/ForeverTracker/releases/download/v<version>/ForeverTracker-Setup-<version>.exe
   UPLOADER_SHA256=<hash of the signed installer>
   UPLOADER_SIGNED=true
   ```

The website's Download page button switches to the new installer immediately; installed apps
update within a day. Azure renews its short-lived certificates with the same publisher name, so updates keep
working; signing with a different identity would change the publisher, and installed apps would refuse the update.

## What the user can do after install

| Action | How |
|---|---|
| See it's running | The tray icon (click it for status and when it last synced), or Start menu → ForeverTracker (starts it if needed and says so) |
| Quit it | Tray icon → **Quit ForeverTracker** (it starts again at the next sign-in if start-with-Windows is on) |
| Turn off auto-start | Settings → Apps → Startup → ForeverTracker → Off |
| Pause / check / see what's uploaded | `ForeverTrackerUploader.exe pause` / `status` / `disclose`, or `ForeverTrackerUploader.exe gui` for a status window |
| Read the log | `%APPDATA%\ForeverTracker\uploader\uploader.log` |
| Turn off self-update | Set `"auto_update": false` in `%APPDATA%\ForeverTracker\uploader\config.json` |
| Uninstall | Add/Remove Programs → ForeverTracker (the addon stays; remove it in CurseForge or the AddOns folder) |

> **Note:** the packaged exe includes Tkinter for the cards (the notice and the tray icon's status
> card, in the site's style). The tray icon itself uses the Windows API directly, with no extra libraries.

## Note on CurseForge

CurseForge distributes **addon files only** — it can't carry this exe, and it can't (and shouldn't)
launch a program. The addon lives on CurseForge; point players to your site's Download page for the
app, since the addon cannot upload anything on its own. CurseForge's moderation policy forbids
"external download links for files" but allows links to your own site at the bottom of the
description, so link to the Download page, not straight to the `.exe`.
