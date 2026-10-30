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
# Signed builds also pass -SignedSetupDir: -Stage setup-program writes the installer's own program (what it runs
# from %TEMP%, and the uninstaller) there to be signed, and -Stage installer then embeds the signed copy.
# Release builds come from GitHub Actions (.github/workflows/windows-app.yml), signed with Azure Artifact Signing.

param(
    [ValidateSet("all", "app", "setup-program", "installer")][string]$Stage = "all",
    [switch]$RequireInstaller,
    [string]$SignedSetupDir
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

if ($Stage -in "all", "app") {
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
$defines = @("/DMyAppVersion=$version")
if ($SignedSetupDir) {
    $SignedSetupDir = (New-Item -ItemType Directory -Force $SignedSetupDir).FullName
    $defines += "/DSignedSetupDir=$SignedSetupDir"
}
if ($Stage -eq "setup-program") {
    if (-not ($iscc -and $SignedSetupDir)) { throw "-Stage setup-program needs Inno Setup and -SignedSetupDir" }
    Write-Host "==> Writing the installer's own program to $SignedSetupDir, to be signed"
    # The compiler stops here, asking (on stderr) for the file it just wrote to be signed.
    $ErrorActionPreference = "Continue"
    & $iscc @defines /Q packaging\installer.iss
    $ErrorActionPreference = "Stop"
    if (-not (Get-ChildItem $SignedSetupDir -Filter "uninst-*.e32")) { throw "Inno Setup wrote no program to sign" }
    $global:LASTEXITCODE = 0
    return
}
if ($iscc) {
    Write-Host "==> Building the installer $version with Inno Setup"
    & $iscc @defines packaging\installer.iss
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
    Write-Host "==> Done: dist\ForeverTracker-Setup-$version.exe (sign it, then see 'Releasing an update' in packaging\README.md)"
} elseif ($RequireInstaller) {
    throw "Inno Setup (ISCC.exe) not found"
} else {
    Write-Warning "Inno Setup (ISCC.exe) not found; built the exe only. Install Inno Setup 6 to build the installer."
}
