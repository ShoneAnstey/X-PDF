; Inno Setup script for Inkstone.
;
; Compiles a Windows installer that installs the portable Inkstone.exe and creates
; Start Menu + Desktop shortcuts (with the app icon) plus an uninstaller.
;
; Expects the PyInstaller build to have produced dist\Inkstone.exe first.
; Compile on Windows with: iscc packaging\inkstone_installer.iss
; Output: dist\Inkstone-Setup.exe

#define MyAppName "Inkstone"
#ifndef MyAppVersion
  #define MyAppVersion "0.1.0"
#endif
#define MyAppPublisher "XPC"
#define MyAppExeName "Inkstone.exe"

[Setup]
AppId={{B6E2D7C0-1F4A-4E8C-9A1D-7C3E5A9B0D21}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=Inkstone-Setup
SetupIconFile=icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Per-user install needs no admin rights.
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce
Name: "associate"; Description: "Register Inkstone as a PDF reader (then set it as default in Windows Settings)"; GroupDescription: "File associations:"; Flags: checkedonce

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[InstallDelete]
; Leftovers from when this app was named XPDF. The AppId is unchanged, so
; this installer upgrades old installs in place — clean up the old exe and
; shortcuts that would otherwise linger beside the renamed ones.
Type: files; Name: "{app}\XPDF.exe"
Type: files; Name: "{autodesktop}\XPDF.lnk"
Type: filesandordirs; Name: "{autoprograms}\XPDF"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; Remove the old XPDF ProgID + "Open with" entry left by pre-rename installs.
Root: HKCU; Subkey: "Software\Classes\XPDF.Document"; Flags: deletekey
Root: HKCU; Subkey: "Software\Classes\.pdf\OpenWithProgids"; ValueType: none; ValueName: "XPDF.Document"; Flags: deletevalue
Root: HKCU; Subkey: "Software\Classes\Applications\XPDF.exe"; Flags: deletekey
; ProgID describing an Inkstone-owned PDF document.
Root: HKCU; Subkey: "Software\Classes\Inkstone.Document"; ValueType: string; ValueData: "PDF Document"; Flags: uninsdeletekey; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\Inkstone.Document\DefaultIcon"; ValueType: string; ValueData: "{app}\{#MyAppExeName},0"; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\Inkstone.Document\shell\open\command"; ValueType: string; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: associate
; Advertise Inkstone in the .pdf "Open with" list so the user can pick it as default.
Root: HKCU; Subkey: "Software\Classes\.pdf\OpenWithProgids"; ValueType: string; ValueName: "Inkstone.Document"; ValueData: ""; Flags: uninsdeletevalue; Tasks: associate
; Register the application for the Default Programs UI.
Root: HKCU; Subkey: "Software\Classes\Applications\{#MyAppExeName}\shell\open\command"; ValueType: string; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Flags: uninsdeletekey; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\Applications\{#MyAppExeName}\SupportedTypes"; ValueType: string; ValueName: ".pdf"; ValueData: ""; Tasks: associate

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
