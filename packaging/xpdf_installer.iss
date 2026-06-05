; Inno Setup script for XPDF.
;
; Compiles a Windows installer that installs the portable XPDF.exe and creates
; Start Menu + Desktop shortcuts (with the X icon) plus an uninstaller.
;
; Expects the PyInstaller build to have produced dist\XPDF.exe first.
; Compile on Windows with: iscc packaging\xpdf_installer.iss
; Output: dist\XPDF-Setup.exe

#define MyAppName "XPDF"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "XPC"
#define MyAppExeName "XPDF.exe"

[Setup]
AppId={{B6E2D7C0-1F4A-4E8C-9A1D-7C3E5A9B0D21}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=XPDF-Setup
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
Name: "associate"; Description: "Register XPDF as a PDF reader (then set it as default in Windows Settings)"; GroupDescription: "File associations:"; Flags: checkedonce

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; ProgID describing an XPDF-owned PDF document.
Root: HKCU; Subkey: "Software\Classes\XPDF.Document"; ValueType: string; ValueData: "PDF Document"; Flags: uninsdeletekey; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\XPDF.Document\DefaultIcon"; ValueType: string; ValueData: "{app}\{#MyAppExeName},0"; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\XPDF.Document\shell\open\command"; ValueType: string; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: associate
; Advertise XPDF in the .pdf "Open with" list so the user can pick it as default.
Root: HKCU; Subkey: "Software\Classes\.pdf\OpenWithProgids"; ValueType: string; ValueName: "XPDF.Document"; ValueData: ""; Flags: uninsdeletevalue; Tasks: associate
; Register the application for the Default Programs UI.
Root: HKCU; Subkey: "Software\Classes\Applications\{#MyAppExeName}\shell\open\command"; ValueType: string; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Flags: uninsdeletekey; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\Applications\{#MyAppExeName}\SupportedTypes"; ValueType: string; ValueName: ".pdf"; ValueData: ""; Tasks: associate

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
