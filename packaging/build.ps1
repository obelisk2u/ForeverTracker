# Build the ForeverTracker uploader exe and the Windows installer.
# Run from the repo root in a Python environment that has the uploader installed:
#     pip install -e uploader -e packages/savedvariables pyinstaller
#     .\packaging\build.ps1
#
# Produces:
#     dist\ForeverTrackerUploader.exe          (windowless helper)
#     dist\ForeverTracker-Setup-<version>.exe  (installer; only if Inno Setup is installed)
#
# Sign BOTH exes before distributing (see README.md in this folder).

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

Write-Host "==> Building ForeverTrackerUploader.exe with PyInstaller"
pyinstaller packaging\forevertracker-uploader.spec --noconfirm --distpath dist --workpath build\pyinstaller
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

# One version number: the uploader's __version__ is what the app compares against the server's release.
$version = (Select-String -Path uploader\forevertracker_uploader\__init__.py -Pattern '^__version__ = "(.+)"').Matches[0].Groups[1].Value

$iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if (-not $iscc) {
    foreach ($p in @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe", "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe")) {
        if (Test-Path $p) { $iscc = $p; break }
    }
}
if ($iscc) {
    Write-Host "==> Building the installer $version with Inno Setup"
    & $iscc "/DMyAppVersion=$version" packaging\installer.iss
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
    Write-Host "==> Done: dist\ForeverTracker-Setup-$version.exe (sign it, then see 'Releasing an update' in packaging\README.md)"
} else {
    Write-Warning "Inno Setup (ISCC.exe) not found; built the exe only. Install Inno Setup 6 to build the installer."
}
