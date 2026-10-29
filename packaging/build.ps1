# Build the ForeverTracker uploader exe and the Windows installer.
# Run from the repo root in a Python environment that has the uploader installed:
#     pip install ./packages/savedvariables ./uploader pyinstaller
#     .\packaging\build.ps1
#
# Produces:
#     dist\ForeverTrackerUploader\             (the app: ForeverTrackerUploader.exe and _internal\)
#     dist\ForeverTracker-Setup-<version>.exe  (installer; only if Inno Setup is installed,
#                                               or always with -RequireInstaller, as CI uses)
#
# -Stage app or -Stage installer builds one half, so CI can sign the app before the installer packs it.
# Release builds come from GitHub Actions (.github/workflows/windows-app.yml), signed with Azure Artifact Signing.

param(
    [ValidateSet("all", "app", "installer")][string]$Stage = "all",
    [switch]$RequireInstaller
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

if ($Stage -ne "installer") {
    Write-Host "==> Building ForeverTrackerUploader.exe with PyInstaller"
    pyinstaller packaging\forevertracker-uploader.spec --noconfirm --distpath dist --workpath build\pyinstaller
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
}
if ($Stage -eq "app") { return }

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
} elseif ($RequireInstaller) {
    throw "Inno Setup (ISCC.exe) not found"
} else {
    Write-Warning "Inno Setup (ISCC.exe) not found; built the exe only. Install Inno Setup 6 to build the installer."
}
