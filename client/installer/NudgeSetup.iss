#define MyAppName "CopyBar"
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#define MyAppPublisher "CopyBar"
#define MyAppExeName "CopyBar.exe"

[Setup]
AppId={{8A2CC172-C2CC-4D09-8D30-D785BBC6DD59}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\CopyBar
DefaultGroupName=CopyBar
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=CopyBar-Setup-{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked
Name: "startup"; Description: "Start CopyBar when I sign in"; GroupDescription: "Startup options:"; Flags: unchecked

[Files]
Source: "..\dist\CopyBar\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\CopyBar"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\CopyBar"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userstartup}\CopyBar"; Filename: "{app}\{#MyAppExeName}"; Tasks: startup

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch CopyBar"; Flags: nowait postinstall skipifsilent
