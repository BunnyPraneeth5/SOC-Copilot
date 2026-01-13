; SOC Copilot Windows Installer Script
; =====================================
; Uses Inno Setup to create a professional Windows installer
; 
; Requirements:
;   - Inno Setup 6.x (https://jrsoftware.org/isinfo.php)
;   - Pre-built distribution in dist/SOC Copilot/
;
; Usage:
;   iscc installer/installer.iss
;
; Output:
;   dist/SOC_Copilot_Setup_0.1.0.exe

#define MyAppName "SOC Copilot"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "SOC Copilot Team"
#define MyAppURL "https://github.com/BunnyPraneeth5/SOC-Copilot"
#define MyAppExeName "SOC Copilot.exe"

[Setup]
; Application metadata
AppId={{8B3F4A2E-5C1D-4E7F-9A2B-3D4E5F6A7B8C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; Installation settings
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
OutputDir=..\dist
OutputBaseFilename=SOC_Copilot_Setup_{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern

; Privileges (install to user folder by default, no admin required)
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; Appearance
SetupIconFile=..\assets\icon.ico
WizardImageFile=compiler:WizModernImage.bmp
WizardSmallImageFile=compiler:WizModernSmallImage.bmp

; Architecture
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startmenuicon"; Description: "Create Start Menu shortcut"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
; Main application files from PyInstaller output
Source: "..\dist\SOC Copilot\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Create writable directories
Source: "..\dist\SOC Copilot\logs\*"; DestDir: "{app}\logs"; Flags: ignoreversion recursesubdirs createallsubdirs; Permissions: users-modify
Source: "..\dist\SOC Copilot\data\*"; DestDir: "{app}\data"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
; Ensure logs directory exists and is writable
Name: "{app}\logs"; Permissions: users-modify
Name: "{app}\logs\system"; Permissions: users-modify

[Icons]
; Start menu shortcut
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startmenuicon
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"

; Desktop shortcut (optional)
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Option to launch after install
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
// Custom code for installation validation

function InitializeSetup(): Boolean;
begin
  Result := True;
  
  // Check for minimum Windows version (Windows 10)
  if not IsWin64 then
  begin
    MsgBox('SOC Copilot requires a 64-bit version of Windows.', mbError, MB_OK);
    Result := False;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    // Create logs directory if it doesn't exist
    ForceDirectories(ExpandConstant('{app}\logs\system'));
  end;
end;

[UninstallDelete]
; Clean up logs on uninstall (optional - commented out to preserve user data)
; Type: filesandordirs; Name: "{app}\logs"

[Messages]
WelcomeLabel2=This will install [name/ver] on your computer.%n%nSOC Copilot is an offline Security Operations Center analysis tool with hybrid ML detection.%n%nNo administrator privileges required for default installation.
