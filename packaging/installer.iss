; ForeverTracker installer (Inno Setup 6).
;
; One download that installs two things the player can see and remove:
;   1. the ForeverTracker addon, into <game folder>\Interface\AddOns\ForeverTracker
;   2. ForeverTrackerUploader.exe, a background app with a tray icon that uploads each run as the game
;      saves it, plus a Start menu shortcut (searchable in Windows) and an optional desktop shortcut
;
; Build:  build the exe first (see build.ps1), then compile this with ISCC.exe installer.iss
; Sign:   sign dist\ForeverTrackerUploader\ForeverTrackerUploader.exe AND the finished installer (CI does both).
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
; What the app uploads, shown before anything is installed.
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
SetupIconFile=..\uploader\forevertracker_uploader\assets\forevertracker.ico
UninstallDisplayIcon={app}\{#MyAppExe}
; Every install writes "Setup Log <date> #<n>.txt" to %TEMP%, so a failed install can be diagnosed.
SetupLogging=yes
; SignTool=mysigner  ; configure in the Inno IDE/ISCC to sign the installer and the uninstaller

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "startup"; Description: "Start {#MyAppName} when I sign in to Windows and upload my dungeon runs automatically"; GroupDescription: "After install:"
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[InstallDelete]
; The app's libraries are replaced as a whole, so an update never leaves an older version's files behind.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
; The app: ForeverTrackerUploader.exe and its _internal folder (PyInstaller one-dir build).
Source: "..\dist\ForeverTrackerUploader\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; The addon, copied into the game's AddOns folder chosen on the custom page, only if it is not there yet
; (see PrepareToInstall). Left in place on uninstall, since CurseForge may be managing it by then.
Source: "..\addon\ForeverTracker\*"; DestDir: "{code:AddonsDir}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs uninsneveruninstall; Check: ShouldInstallAddon

[Registry]
; Start-with-Windows (per-user, visible in Startup settings). Removed on uninstall.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; \
    ValueName: "ForeverTrackerUploader"; ValueData: """{app}\{#MyAppExe}"" background"; \
    Tasks: startup; Flags: uninsdeletevalue

[Icons]
; Start menu (which is also what Windows search finds) and, if chosen, the desktop. Both start the app
; and show a notice that it is running (or already was); its tray icon then offers Quit.
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Parameters: "start"; \
    Comment: "Upload your dungeon runs to ForeverTracker"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Parameters: "start"; \
    Comment: "Upload your dungeon runs to ForeverTracker"; Tasks: desktopicon

[Run]
; The installer starts no hidden programs or scripts: antivirus heuristics treat that as malware behaviour.
; The app's settings are left in installer.json instead (see SaveAppChoices).
; "Start ForeverTracker" on the last page (ticked), so there is no need to sign out first. Not runhidden:
; that would hide the app's first window, the notice.
Filename: "{app}\{#MyAppExe}"; Parameters: "start"; \
    Flags: nowait postinstall skipifsilent; Description: "Start {#MyAppName}"
; After a self-update, start the new version (the old one exited so its exe could be replaced).
Filename: "{app}\{#MyAppExe}"; Parameters: "background"; Flags: nowait; Check: IsUpdate

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

// A game folder: Battle.net puts Wow.exe and .flavor.info there when it downloads the game; Interface and
// WTF only appear once the game has been played, so a fresh download has neither.
function DirHasGame(Dir: String): Boolean;
begin
  Result := FileExists(Dir + '\Wow.exe') or FileExists(Dir + '\.flavor.info') or
    DirExists(Dir + '\Interface') or DirExists(Dir + '\WTF');
end;

// Returns <Root>\_forever_ if that folder holds the game, otherwise ''.
function ForeverIn(Root: String): String;
begin
  Result := '';
  if (Root <> '') and DirHasGame(AddBackslash(Root) + ForeverFolder) then
    Result := AddBackslash(Root) + ForeverFolder;
end;

// The World of Warcraft folder of Battle.net's uninstall entries ("World of Warcraft", "... Classic Era", ...),
// which all share one root. Looks in both registry views.
function ForeverInUninstallEntries(): String;
var
  Keys: TArrayOfString;
  I, View: Integer;
  Base, Name, Location: String;
begin
  Result := '';
  Base := 'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall';
  for View := 0 to 1 do
  begin
    if ((View = 0) and RegGetSubkeyNames(HKLM32, Base, Keys)) or
       ((View = 1) and IsWin64 and RegGetSubkeyNames(HKLM64, Base, Keys)) then
      for I := 0 to GetArrayLength(Keys) - 1 do
        if Pos('Warcraft', Keys[I]) > 0 then
        begin
          if View = 0 then
          begin
            if not RegQueryStringValue(HKLM32, Base + '\' + Keys[I], 'DisplayName', Name) then Name := '';
            if not RegQueryStringValue(HKLM32, Base + '\' + Keys[I], 'InstallLocation', Location) then Location := '';
          end else begin
            if not RegQueryStringValue(HKLM64, Base + '\' + Keys[I], 'DisplayName', Name) then Name := '';
            if not RegQueryStringValue(HKLM64, Base + '\' + Keys[I], 'InstallLocation', Location) then Location := '';
          end;
          if (Pos('Warcraft', Name) > 0) and (Location <> '') then
          begin
            Result := ForeverIn(RemoveBackslashUnlessRoot(Location));
            if Result <> '' then exit;
          end;
        end;
  end;
end;

function GetDriveTypeW(RootPathName: String): Cardinal;
  external 'GetDriveTypeW@kernel32.dll stdcall';

// Common places for the World of Warcraft folder, on every fixed drive (not CD, network or card readers,
// which can be slow or prompt for a disk).
function ForeverOnAnyDrive(): String;
var
  Letter, I: Integer;
  Drive: String;
  Places: array of String;
begin
  Result := '';
  Places := ['World of Warcraft', 'Program Files (x86)\World of Warcraft', 'Program Files\World of Warcraft',
    'Games\World of Warcraft', 'Battle.net\World of Warcraft', 'Blizzard\World of Warcraft',
    'Games\Blizzard\World of Warcraft', 'Blizzard Games\World of Warcraft', 'Games\Battle.net\World of Warcraft'];
  for Letter := Ord('C') to Ord('Z') do
  begin
    Drive := Chr(Letter) + ':\';
    if GetDriveTypeW(Drive) = 3 then // DRIVE_FIXED
      for I := 0 to GetArrayLength(Places) - 1 do
      begin
        Result := ForeverIn(Drive + Places[I]);
        if Result <> '' then exit;
      end;
  end;
end;

function DetectGameDir(): String;
var
  InstallPath: String;
begin
  Result := '';
  // Battle.net records the most recently installed flavor here (e.g. ...\World of Warcraft\_forever_\),
  // and every flavor folder sits under the same World of Warcraft root.
  if RegQueryStringValue(HKLM32, 'SOFTWARE\Blizzard Entertainment\World of Warcraft', 'InstallPath', InstallPath) then
  begin
    InstallPath := RemoveBackslashUnlessRoot(InstallPath);
    Result := ForeverIn(ExtractFileDir(InstallPath));
    if Result = '' then
      Result := ForeverIn(InstallPath);
  end;
  if Result = '' then
    Result := ForeverInUninstallEntries();
  if Result = '' then
    Result := ForeverOnAnyDrive();
  // Not found: suggest the default location; the user corrects it on the page (Browse).
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
      Result := MsgBox('That folder does not look like a WoW game folder (no Wow.exe, Interface or WTF).' + #13#10 +
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

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  RC: Integer;
begin
  Result := '';
  // The addon is only added when it is missing. Once installed, CurseForge keeps it up to date, so
  // reinstalls and self-updates never overwrite (or downgrade) it.
  InstallAddon := (not IsUpdate()) and not FileExists(AddonsDir('') + '\ForeverTracker.toc');
  // Stop a running uploader so its exe can be replaced (a first install has none to stop). After a
  // self-update it has normally exited already.
  if FileExists(ExpandConstant('{app}\{#MyAppExe}')) then
    Exec(ExpandConstant('{sys}\taskkill.exe'), '/im {#MyAppExe} /f', '', SW_HIDE, ewWaitUntilTerminated, RC);
end;

// S as a JSON string, in plain ASCII (\u escapes), so it reads the same in any encoding.
function JsonString(S: String): String;
var
  I: Integer;
begin
  Result := '"';
  for I := 1 to Length(S) do
    if (S[I] = '"') or (S[I] = '\') then
      Result := Result + '\' + S[I]
    else if (Ord(S[I]) < 32) or (Ord(S[I]) > 126) then
      Result := Result + Format('\u%.4x', [Ord(S[I])])
    else
      Result := Result + S[I];
  Result := Result + '"';
end;

// The server and the chosen game folder, which the app saves to its config.json when it next starts.
procedure SaveAppChoices();
var
  Dir: String;
begin
  Dir := ExpandConstant('{userappdata}\ForeverTracker\uploader');
  ForceDirectories(Dir);
  SaveStringToFile(Dir + '\installer.json',
    '{"server_url": ' + JsonString('{#ServerURL}') + ', "wow_paths": [' + JsonString(GameDir('')) + ']}', False);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  // A self-update keeps the settings the player already has.
  if (CurStep = ssPostInstall) and not IsUpdate() then
    SaveAppChoices();
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  // A game that is already open only loads a new addon after a restart.
  if (CurPageID = wpFinished) and InstallAddon then
    WizardForm.FinishedLabel.Caption := WizardForm.FinishedLabel.Caption + #13#10#13#10 +
      'If World of Warcraft is open, restart it to load the ForeverTracker addon.';
end;
