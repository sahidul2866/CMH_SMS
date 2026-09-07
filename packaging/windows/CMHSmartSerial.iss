#ifndef SourceRoot
  #error SourceRoot must be supplied by BUILD_WINDOWS_INSTALLER.bat
#endif

[Setup]
AppId={{E7AA7C11-EDAD-4C31-9CF0-496BCE20352D}
AppName=CMH Smart Serial
AppVersion=1.0.0
AppPublisher=Combined Military Hospital
DefaultDirName={autopf}\CMH Smart Serial
DefaultGroupName=CMH Smart Serial
OutputDir={#SourceRoot}\installer-output
OutputBaseFilename=CMH-Smart-Serial-Setup
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
WizardStyle=modern
UninstallDisplayIcon={app}\CMHSmartSerial.exe

[Files]
Source: "{#SourceRoot}\packaging-dist\CMH Smart Serial\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SourceRoot}\packaging\windows\install_autostart.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\THIRD_PARTY_MODELS.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\CMH Smart Serial"; Filename: "{app}\CMHSmartSerial.exe"
Name: "{commondesktop}\CMH Smart Serial"; Filename: "{app}\CMHSmartSerial.exe"

[Run]
Filename: "netsh"; Parameters: "advfirewall firewall add rule name=""CMH Smart Serial 8100"" dir=in action=allow protocol=TCP localport=8100 profile=private"; Flags: runhidden
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\install_autostart.ps1"""; Flags: runhidden waituntilterminated

[UninstallRun]
Filename: "schtasks.exe"; Parameters: "/End /TN ""CMH Smart Serial Server"""; Flags: runhidden; RunOnceId: "StopTask"
Filename: "schtasks.exe"; Parameters: "/Delete /TN ""CMH Smart Serial Server"" /F"; Flags: runhidden; RunOnceId: "DeleteTask"

[UninstallDelete]
; Operational data intentionally remains under ProgramData for upgrades/recovery.
Type: filesandordirs; Name: "{app}"
