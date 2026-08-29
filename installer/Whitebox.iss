; Whitebox Writing local bundle installer.
; The application remains local and uses the user's existing WSL runtime.

#define AppName "Whitebox Writing"
#define AppVersion "0.2.0"
#define Publisher "Whitebox"
#define LauncherDir "..\launcher"
#define ProjectRoot ".."

[Setup]
AppId={{D3E2C7F7-3F52-4E26-9DA4-7F8D9B5E9A10}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#Publisher}
DefaultDirName={localappdata}\Whitebox Writing
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=Whitebox-Writing-{#AppVersion}-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName={#AppName} {#AppVersion}
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes
CloseApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "{#ProjectRoot}\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#ProjectRoot}\package.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#ProjectRoot}\package-lock.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#ProjectRoot}\apps\api\pyproject.toml"; DestDir: "{app}\apps\api"; Flags: ignoreversion
Source: "{#ProjectRoot}\apps\api\whitebox\*.py"; DestDir: "{app}\apps\api\whitebox"; Flags: ignoreversion
Source: "{#ProjectRoot}\apps\web\package.json"; DestDir: "{app}\apps\web"; Flags: ignoreversion
Source: "{#ProjectRoot}\apps\web\src\*"; DestDir: "{app}\apps\web\src"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#ProjectRoot}\apps\web\index.html"; DestDir: "{app}\apps\web"; Flags: ignoreversion
Source: "{#ProjectRoot}\apps\web\vite.config.ts"; DestDir: "{app}\apps\web"; Flags: ignoreversion
Source: "{#ProjectRoot}\apps\web\tsconfig.json"; DestDir: "{app}\apps\web"; Flags: ignoreversion
Source: "{#ProjectRoot}\apps\web\tsconfig.app.json"; DestDir: "{app}\apps\web"; Flags: ignoreversion
Source: "{#ProjectRoot}\apps\web\tsconfig.node.json"; DestDir: "{app}\apps\web"; Flags: ignoreversion
Source: "{#ProjectRoot}\launcher\WhiteboxLauncher.ps1"; DestDir: "{app}\launcher"; Flags: ignoreversion
Source: "{#ProjectRoot}\launcher\启动Whitebox.bat"; DestDir: "{app}\launcher"; Flags: ignoreversion
Source: "{#ProjectRoot}\launcher\README.md"; DestDir: "{app}\launcher"; Flags: ignoreversion
Source: "{#ProjectRoot}\docs\*"; DestDir: "{app}\docs"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#ProjectRoot}\installer\Whitebox.iss"; DestDir: "{app}\installer"; Flags: ignoreversion
Source: "{#ProjectRoot}\installer\构建安装包.bat"; DestDir: "{app}\installer"; Flags: ignoreversion

[Icons]
Name: "{autodesktop}\Whitebox Writing"; Filename: "{app}\launcher\启动Whitebox.bat"; WorkingDir: "{app}\launcher"; Comment: "Local Whitebox AI writing workflow"
Name: "{group}\Whitebox Writing"; Filename: "{app}\launcher\启动Whitebox.bat"; WorkingDir: "{app}\launcher"; Comment: "Local Whitebox AI writing workflow"
Name: "{group}\Whitebox Launcher README"; Filename: "{app}\launcher\README.md"

[Run]
Filename: "{app}\launcher\启动Whitebox.bat"; WorkingDir: "{app}\launcher"; Description: "Launch Whitebox Writing"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\launcher\WhiteboxLauncher.ps1"" -StopServices"; Flags: runhidden waituntilterminated; RunOnceId: "StopWhiteboxServices"

[UninstallDelete]
Type: filesandordirs; Name: "{app}\launcher\runtime"
Type: filesandordirs; Name: "{app}\launcher\settings.json"
