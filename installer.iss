#ifndef BuildDir
  #define BuildDir "dist\CYRUS"
#endif

#define AppVersion "1.0.0"

[Setup]
AppId={{B161D0D9-73EA-4A4E-909C-431B8A8B5C9B}
AppName=CYRUS
AppVersion={#AppVersion}
AppPublisher=CYRUS
DefaultDirName={autopf}\CYRUS
DefaultGroupName=CYRUS
UninstallDisplayName=CYRUS
UninstallDisplayIcon={app}\CYRUS.exe
OutputDir=dist\installer
OutputBaseFilename=CYRUS-Setup
SetupIconFile=assets\cyrus.ico
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
CloseApplications=yes
DisableProgramGroupPage=yes
SetupLogging=yes
VersionInfoDescription=CYRUS Windows Assistant Setup
VersionInfoProductName=CYRUS
VersionInfoProductVersion={#AppVersion}
VersionInfoCompany=CYRUS

[Types]
Name: "full"; Description: "Full installation"
Name: "custom"; Description: "Custom installation"; Flags: iscustom

[Components]
Name: "core"; Description: "CYRUS assistant, dashboard, typed chat, timers, and local system tools"; Types: full custom; Flags: fixed
Name: "alan_voice"; Description: "Alan local speech output (download the voice separately)"; Types: full
Name: "microphone_input"; Description: "Microphone speech input (Google online transcription; mic starts muted)"; Types: full
Name: "web_news"; Description: "Web search and current-news results (internet required)"; Types: full
Name: "vlc_music"; Description: "Music search and playback (VLC must be installed separately)"; Types: full
Name: "screen_analysis"; Description: "Screen analysis through OpenRouter (screenshots are sent online when requested)"; Types: full

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "{#BuildDir}\CYRUS.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#BuildDir}\_internal\*"; DestDir: "{app}\_internal"; Excludes: "voices\*"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#BuildDir}\.env.example"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#BuildDir}\api_keys.example.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#BuildDir}\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#BuildDir}\download_ollama_model.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#BuildDir}\download_alan_voice.ps1"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\CYRUS"; Filename: "{app}\CYRUS.exe"; IconFilename: "{app}\CYRUS.exe"
Name: "{autodesktop}\CYRUS"; Filename: "{app}\CYRUS.exe"; Tasks: desktopicon

[Run]
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -NoExit -File ""{app}\download_ollama_model.ps1"""; Description: "Download the local AI model llama3.2:3b (several GB; internet required)"; Flags: postinstall runasoriginaluser unchecked nowait
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\download_alan_voice.ps1"""; Description: "Download Alan Piper voice files from Hugging Face (about 63 MB)"; Flags: postinstall runasoriginaluser unchecked; Check: ShouldOfferVoiceDownload
Filename: "{app}\CYRUS.exe"; Description: "Launch CYRUS"; Flags: postinstall nowait skipifsilent runasoriginaluser

[UninstallDelete]
Type: files; Name: "{app}\features.json"

[Code]
function JsonBoolean(Value: Boolean): String;
begin
  if Value then
    Result := 'true'
  else
    Result := 'false';
end;

procedure WriteInstalledFeatures;
var
  FeatureConfiguration: String;
begin
  FeatureConfiguration :=
    '{' + #13#10 +
    '  "alan_voice": ' + JsonBoolean(WizardIsComponentSelected('alan_voice')) + ',' + #13#10 +
    '  "microphone_input": ' + JsonBoolean(WizardIsComponentSelected('microphone_input')) + ',' + #13#10 +
    '  "web_news": ' + JsonBoolean(WizardIsComponentSelected('web_news')) + ',' + #13#10 +
    '  "vlc_music": ' + JsonBoolean(WizardIsComponentSelected('vlc_music')) + ',' + #13#10 +
    '  "screen_analysis": ' + JsonBoolean(WizardIsComponentSelected('screen_analysis')) + #13#10 +
    '}' + #13#10;

  if not SaveStringToFile(ExpandConstant('{app}\features.json'), FeatureConfiguration, False) then
    RaiseException('Could not save the selected CYRUS features.');
end;

function ShouldOfferVoiceDownload: Boolean;
begin
  Result := WizardIsComponentSelected('alan_voice');
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    WriteInstalledFeatures;
end;
