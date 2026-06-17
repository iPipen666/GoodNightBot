; GoodNightBot — инсталлер (Inno Setup 6). Компиляция: ISCC.exe GoodNightBot.iss
; Ставит в %LOCALAPPDATA%\GoodNightBot (без админ-прав; venv пишется туда же на 1-м запуске).
; GoodNightBot.exe при первом старте сам создаёт venv и ставит зависимости (bootstrap).

#define AppName "GoodNightBot"
#define AppVer  "1.1.16"
#define AppExe  "GoodNightBot.exe"

[Setup]
AppName={#AppName}
AppVersion={#AppVer}
AppPublisher=SQll.ART
DefaultDirName={localappdata}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=installer
OutputBaseFilename=GoodNightBot-Setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Ярлыки:"

[Files]
Source: "{#AppExe}";            DestDir: "{app}"; Flags: ignoreversion
Source: "bootstrap.py";         DestDir: "{app}"; Flags: ignoreversion
Source: "requirements.txt";     DestDir: "{app}"; Flags: ignoreversion
Source: "VERSION";              DestDir: "{app}"; Flags: ignoreversion
Source: "icon.ico";             DestDir: "{app}"; Flags: ignoreversion
Source: "*.py";                 DestDir: "{app}"; Flags: ignoreversion
; *.json кроме оконно-зависимых калибровок: их нельзя шарить между юзерами (сняты на окне разработчика
; → у нового юзера дали бы ложный статус «откалибровано» и промахи по UI). Каждый калибрует сам, 1 раз.
Source: "*.json";               DestDir: "{app}"; Excludes: "records_calibration.json,chest_calibration.json,calibration.json,inv_calibration.json,auto_calibration.json,stash_calibration.json,panel_toggles.json,portal_calibration.json,records_ctl.json"; Flags: ignoreversion
Source: "fonts\*";               DestDir: "{app}\fonts";           Flags: ignoreversion recursesubdirs createallsubdirs
Source: "templates\*";          DestDir: "{app}\templates";       Flags: ignoreversion recursesubdirs createallsubdirs
Source: "game_textassets\*";    DestDir: "{app}\game_textassets"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}";        Filename: "{app}\{#AppExe}"; IconFilename: "{app}\icon.ico"
Name: "{userdesktop}\{#AppName}";  Filename: "{app}\{#AppExe}"; IconFilename: "{app}\icon.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Запустить {#AppName}"; Flags: nowait postinstall skipifsilent

; OCR (Tesseract + рус) ставится АВТОМАТИЧЕСКИ при первом запуске (bootstrap скачает
; и положит локально в .tesseract). Ручная установка не нужна.
