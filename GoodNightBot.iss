; GoodNightBot — инсталлер (Inno Setup 6). Компиляция: ISCC.exe GoodNightBot.iss
; Ставит в %LOCALAPPDATA%\GoodNightBot (без админ-прав; venv пишется туда же на 1-м запуске).
; GoodNightBot.exe при первом старте сам создаёт venv и ставит зависимости (bootstrap).

#define AppName "GoodNightBot"
#define AppVer  "1.1.22"
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
; вложенный установщик Python 3.12 — чтобы не зависеть от скачивания (главная причина «проблемы с питоном»)
Source: "python-setup.exe";     DestDir: "{app}"; Flags: ignoreversion
Source: "bootstrap.py";         DestDir: "{app}"; Flags: ignoreversion
Source: "requirements.txt";     DestDir: "{app}"; Flags: ignoreversion
Source: "VERSION";              DestDir: "{app}"; Flags: ignoreversion
Source: "icon.ico";             DestDir: "{app}"; Flags: ignoreversion
Source: "*.py";                 DestDir: "{app}"; Flags: ignoreversion
; *.json кроме оконно-зависимых калибровок: их нельзя шарить между юзерами (сняты на окне разработчика
; → у нового юзера дали бы ложный статус «откалибровано» и промахи по UI). Каждый калибрует сам, 1 раз.
Source: "*.json";               DestDir: "{app}"; Excludes: "records_calibration.json,chest_calibration.json,calibration.json,inv_calibration.json,auto_calibration.json,stash_calibration.json,panel_toggles.json,portal_calibration.json,records_ctl.json,game_settings_calibration.json,scan_snapshot.json,custom_routines.json"; Flags: ignoreversion
Source: "fonts\*";               DestDir: "{app}\fonts";           Flags: ignoreversion recursesubdirs createallsubdirs
Source: "templates\*";          DestDir: "{app}\templates";       Flags: ignoreversion recursesubdirs createallsubdirs
Source: "game_textassets\*";    DestDir: "{app}\game_textassets"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "models\*";             DestDir: "{app}\models";          Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}";        Filename: "{app}\{#AppExe}"; IconFilename: "{app}\icon.ico"
Name: "{userdesktop}\{#AppName}";  Filename: "{app}\{#AppExe}"; IconFilename: "{app}\icon.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Запустить {#AppName}"; Flags: nowait postinstall skipifsilent

; OCR (Tesseract + рус) ставится АВТОМАТИЧЕСКИ при первом запуске (bootstrap скачает
; и положит локально в .tesseract). Ручная установка не нужна.

[Code]
// Чистый апгрейд с ранних (до-1.1.19) сборок: их venv мог быть собран на несовместимом Python
// (3.13/3.14 → rapidocr не ставился) или без зависимостей. Признак старой сборки — НЕТ OCR-модели.
// В этом случае сносим venv ДО копирования файлов → bootstrap пересоберёт его начисто на 1-м запуске
// (лаунчер 1.1.19 берёт Python ≤3.12). Свежие (1.1.19+) сборки venv НЕ трогаем — апдейты быстрые.
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
  begin
    if DirExists(ExpandConstant('{app}\.venv')) and
       (not FileExists(ExpandConstant('{app}\models\ocr\eslav\rec.onnx'))) then
      DelTree(ExpandConstant('{app}\.venv'), True, True, True);
  end;
end;
