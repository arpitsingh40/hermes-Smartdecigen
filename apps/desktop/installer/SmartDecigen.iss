; One-click, per-user (no admin) Windows installer for SmartDecigen.
; Wraps the electron-builder `win-unpacked` tree of the bundled desktop build
; (Electron app + Python runtime + Hermes/SmartDecigen payload).
;
; iscc /DAppVersion=1.2.3 /DSourceDir=<win-unpacked> /DAppExe=<exe name> /DOutputDir=<dir> SmartDecigen.iss

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\release\win-unpacked"
#endif
#ifndef AppExe
  #define AppExe "SmartDecigen.exe"
#endif
#ifndef OutputDir
  #define OutputDir "..\release"
#endif

#define AppName "SmartDecigen"

[Setup]
AppId={{6F4B7D2E-3C1A-4E8B-9D5F-5DEC16E00001}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppName}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir={#OutputDir}
OutputBaseFilename={#AppName}-Setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
LZMAUseSeparateProcess=yes
WizardStyle=modern
CloseApplications=force
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; Upgrades replace the whole app tree so stale payload files never mix with new ones.
; User data lives in %LOCALAPPDATA%\hermes and is never touched.
Type: filesandordirs; Name: "{app}\resources"
Type: files; Name: "{app}\*.exe"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
