; ForeverTracker installer (Inno Setup 6).
;
; One download that installs two things the player can see and remove:
;   1. the ForeverTracker addon, into <game folder>\Interface\AddOns\ForeverTracker
;   2. ForeverTrackerUploader.exe, a windowless helper that uploads each run as the game saves it
;
; Build:  build the exe first (see build.ps1), then compile this with ISCC.exe installer.iss
; Sign:   sign dist\ForeverTrackerUploader.exe AND the finished installer before distributing.
;
; Design notes that keep this on the right side of the line:
;   * No admin required: installs under %LOCALAPPDATA% and uses the per-user Run key, so the
;     start-with-Windows entry is visible in Settings > Apps > Startup and can be turned off there.
;   * Start-with-Windows is a checkbox the user sees, not a silent default decision.
;   * The uninstaller removes the autostart entry, stops the helper, and deletes the app. The addon
;     stays: after install it belongs to the player, and CurseForge keeps it up to date.
;
; Self-update: the running app downloads a newer installer, checks it is signed by the same publisher,
; and runs it with /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /UPDATE=1. Update mode keeps the existing
; settings, never touches the addon, and starts the new version when done.

#define MyAppName "ForeverTracker"
; build.ps1 passes the uploader's __version__ (/DMyAppVersion=...), so the two always match.
#ifndef MyAppVersion
  #define MyAppVersion "0.1.0"
#endif
#define MyPublisher "ForeverTracker"
#define MyAppExe "ForeverTrackerUploader.exe"
; Replace with your real site before building a public installer:
#define ServerURL "https://forevertracker.org"

[Setup]
AppId={{B8F2C1A4-6E3D-4E7A-9C2B-7F1A2D3E4B50}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyPublisher}
AppPublisherURL=https://github.com/obelisk2u/ForeverTracker
VersionInfoVersion={#MyAppVersion}
VersionInfoProductName={#MyAppName}
VersionInfoDescription={#MyAppName} installer
; What the app uploads, shown before anything is installed (SignPath Foundation requires this for
; software that sends data).
InfoBeforeFile=privacy.txt
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=ForeverTracker-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; SignTool=mysigner  ; configure in the Inno IDE/ISCC to sign the installer and the uninstaller

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "startup"; Description: "Start {#MyAppName} when I sign in to Windows and upload my dungeon runs automatically"; GroupDescription: "After install:"

[Files]
; The uploader exe.
Source: "..\dist\{#MyAppExe}"; DestDir: "{app}"; Flags: ignoreversion
; The addon, copied into the game's AddOns folder chosen on the custom page, only if it is not there yet
; (see PrepareToInstall). Left in place on uninstall, since CurseForge may be managing it by then.
Source: "..\addon\ForeverTracker\*"; DestDir: "{code:AddonsDir}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs uninsneveruninstall; Check: ShouldInstallAddon

[Registry]
; Start-with-Windows (per-user, visible in Startup settings). Removed on uninstall.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; \
    ValueName: "ForeverTrackerUploader"; ValueData: """{app}\{#MyAppExe}"" background"; \
    Tasks: startup; Flags: uninsdeletevalue

[Run]
; Write the uploader's config (server URL + the chosen game folder). Read-only toward the game.
; A self-update keeps the settings the player already has.
Filename: "{app}\{#MyAppExe}"; Parameters: "setup --server ""{#ServerURL}"" --wow ""{code:GameDir}"""; \
    Flags: runhidden waituntilterminated; Check: not IsUpdate
; Start it now so there is no need to reboot, only if the user left the startup box ticked.
Filename: "{app}\{#MyAppExe}"; Parameters: "background"; Tasks: startup; \
    Flags: nowait runhidden postinstall skipifsilent; Description: "Start {#MyAppName} now"
; After a self-update, start the new version (the old one exited so its exe could be replaced).
Filename: "{app}\{#MyAppExe}"; Parameters: "background"; Flags: nowait runhidden; Check: IsUpdate

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/im {#MyAppExe} /f"; Flags: runhidden; RunOnceId: "StopUploader"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
const
  // Forever's flavor folder inside the World of Warcraft install (product "wowf", client 1.60.1).
  ForeverFolder = '_forever_';

var
  GamePage: TInputDirWizardPage;
  InstallAddon: Boolean;

// True when the running app started this installer to update itself.
function IsUpdate(): Boolean;
begin
  Result := ExpandConstant('{param:update|0}') = '1';
end;

function ShouldInstallAddon(): Boolean;
begin
  Result := InstallAddon;
end;

function DirHasGame(Dir: String): Boolean;
begin
  Result := DirExists(Dir + '\Interface') or DirExists(Dir + '\WTF');
end;

// Returns <Root>\_forever_ if that folder holds the game, otherwise ''.
function ForeverIn(Root: String): String;
begin
  Result := '';
  if (Root <> '') and DirHasGame(AddBackslash(Root) + ForeverFolder) then
    Result := AddBackslash(Root) + ForeverFolder;
end;

function DetectGameDir(): String;
var
  InstallPath: String;
begin
  Result := '';
  // Battle.net records the most recently installed flavor here (e.g. ...\World of Warcraft\_forever_\),
  // and every flavor folder sits under the same World of Warcraft root. This finds installs on any drive.
  if RegQueryStringValue(HKLM32, 'SOFTWARE\Blizzard Entertainment\World of Warcraft', 'InstallPath', InstallPath) then
  begin
    InstallPath := RemoveBackslashUnlessRoot(InstallPath);
    Result := ForeverIn(ExtractFileDir(InstallPath));
    if Result = '' then
      Result := ForeverIn(InstallPath);
  end;
  if Result = '' then
    Result := ForeverIn(ExpandConstant('{commonpf32}\World of Warcraft'));
  if (Result = '') and IsWin64 then
    Result := ForeverIn(ExpandConstant('{commonpf64}\World of Warcraft'));
  // Not found: suggest the default location; the user corrects it on the page.
  if Result = '' then
    Result := ExpandConstant('{commonpf32}\World of Warcraft\') + ForeverFolder;
end;

procedure InitializeWizard();
begin
  GamePage := CreateInputDirPage(wpSelectDir,
    'World of Warcraft: Forever folder',
    'Where is your game installed?',
    'This is the ' + ForeverFolder + ' folder inside World of Warcraft. The addon is copied into its' + #13#10 +
    'Interface\AddOns folder, where the game turns it on by default. Nothing else in the folder is modified.',
    False, '');
  GamePage.Add('');
  GamePage.Values[0] := DetectGameDir();
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  // Silent installs call this too, and returning False would abort the update; an update never
  // installs the addon, so the folder does not matter then.
  if (CurPageID = GamePage.ID) and not IsUpdate() then
  begin
    if not DirExists(GamePage.Values[0]) then
    begin
      MsgBox('That folder does not exist. Please choose your World of Warcraft: Forever folder.', mbError, MB_OK);
      Result := False;
    end
    else if not DirHasGame(GamePage.Values[0]) then
      Result := MsgBox('That folder does not look like a WoW game folder (no Interface or WTF folder).' + #13#10 +
        'Install the addon there anyway?', mbConfirmation, MB_YESNO) = IDYES
    else if CompareText(ExtractFileName(RemoveBackslashUnlessRoot(GamePage.Values[0])), ForeverFolder) <> 0 then
      // Another flavor (e.g. _retail_): the addon would never load in Forever.
      Result := MsgBox('That is not the Forever folder (' + ForeverFolder + '), so Forever will not load the addon from there.' + #13#10 +
        'Install it there anyway?', mbConfirmation, MB_YESNO) = IDYES;
  end;
end;

function GameDir(Param: String): String;
begin
  Result := GamePage.Values[0];
end;

function AddonsDir(Param: String): String;
begin
  Result := GamePage.Values[0] + '\Interface\AddOns\ForeverTracker';
end;

function IsGameRunning(): Boolean;
var
  RC: Integer;
begin
  Result := False;
  // Non-fatal best effort: if PowerShell is unavailable we simply skip the check.
  if Exec('powershell.exe',
      '-NoProfile -ExecutionPolicy Bypass -Command "if (Get-Process -Name Wow* -ErrorAction SilentlyContinue) { exit 1 } else { exit 0 }"',
      '', SW_HIDE, ewWaitUntilTerminated, RC) then
    Result := (RC = 1);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  RC: Integer;
begin
  Result := '';
  // The addon is only added when it is missing. Once installed, CurseForge keeps it up to date, so
  // reinstalls and self-updates never overwrite (or downgrade) it.
  InstallAddon := (not IsUpdate()) and not FileExists(AddonsDir('') + '\ForeverTracker.toc');
  if InstallAddon and IsGameRunning() then
  begin
    Result := 'Please close World of Warcraft before installing, then click Back and Next to continue.' + #13#10 +
      '(Copying an addon while the game is running is unreliable.)';
    exit;
  end;
  // Stop a running uploader so its exe can be replaced. After a self-update it has normally exited already.
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/im {#MyAppExe} /f', '', SW_HIDE, ewWaitUntilTerminated, RC);
end;
